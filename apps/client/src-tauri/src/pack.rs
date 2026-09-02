//! Learner pack verify-before-trust and install.

use crate::db::{EncryptedDb, InstalledPack};
use crate::error::AppError;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;
use zip::ZipArchive;

const INSTRUCTOR_LEAK_HINTS: &[&str] = &[
    "instructor_solution",
    "solution_guide",
    "solution_notes_for_instructors",
    "instructor_notes",
    "answer_key",
    "teaching_notes.md",
    "demo_plan.md",
    "instructor_packet",
];
const PRIVATE_KEY_HINTS: &[&str] = &[
    "private.key",
    "private_key",
    ".pem",
    "TEST_ONLY_ed25519_private",
];
const PLATFORM_VERSION: &str = "0.1.0";

#[derive(Debug, Clone, Deserialize)]
struct SignatureMeta {
    alg: String,
    signature_b64: String,
    signed_payload_sha256: String,
}

#[derive(Debug, Clone, serde::Serialize, Deserialize)]
pub struct LessonInfo {
    pub lesson_id: String,
    pub title: String,
    pub path: String,
    pub week: Option<i64>,
    pub order: Option<i64>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct TrustStatus {
    pub pack_id: String,
    pub module_id: String,
    pub title: String,
    pub verification_status: String,
    pub content_root_sha256: String,
    pub source_commit: String,
    pub trusted: bool,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct LessonContent {
    pub lesson_id: String,
    pub title: String,
    pub path: String,
    pub markdown: String,
    pub resume_scroll_offset: f64,
}

pub struct PackService {
    pub data_dir: PathBuf,
    pub verify_key: VerifyingKey,
    pub db: EncryptedDb,
}

impl PackService {
    pub fn new(data_dir: PathBuf, verify_key_bytes: &[u8], db_key: [u8; 32]) -> Result<Self, AppError> {
        if verify_key_bytes.len() != 32 {
            return Err(AppError::Key("verify key must be 32 bytes".into()));
        }
        let mut arr = [0u8; 32];
        arr.copy_from_slice(verify_key_bytes);
        let verify_key = VerifyingKey::from_bytes(&arr)
            .map_err(|e| AppError::Key(format!("invalid verify key: {e}")))?;
        let db = EncryptedDb::open(&data_dir, db_key)?;
        fs::create_dir_all(data_dir.join("packs"))?;
        Ok(Self {
            data_dir,
            verify_key,
            db,
        })
    }

    pub fn install_pack(&self, source: &Path) -> Result<TrustStatus, AppError> {
        let work = tempfile::tempdir().map_err(|e| AppError::Io(e.to_string()))?;
        let root = materialize_pack(source, work.path())?;
        verify_learner_pack(&root, &self.verify_key)?;
        let manifest: Value = serde_json::from_str(&fs::read_to_string(root.join("learner_pack_manifest.json"))?)?;
        let pack_id = manifest
            .get("pack_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::VerifyBeforeTrust("pack_id missing".into()))?
            .to_string();
        let module_id = manifest
            .get("module_id")
            .and_then(|v| v.as_str())
            .unwrap_or("UNKNOWN")
            .to_string();
        let title = manifest
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or(&module_id)
            .to_string();
        let content_root_sha256 = manifest
            .get("content_root_sha256")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let source_commit = manifest
            .get("source_commit")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let schema_version = manifest
            .get("schema_version")
            .and_then(|v| v.as_str())
            .unwrap_or("1.0.0")
            .to_string();

        // Downgrade protection against already-installed protected version.
        if let Some(existing) = self.db.get_pack(&pack_id)? {
            if existing.content_root_sha256 != content_root_sha256
                && is_downgrade(&existing.content_version, &schema_version)
            {
                return Err(AppError::SchemaDowngrade(format!(
                    "refusing downgrade of {}",
                    pack_id
                )));
            }
        }

        let dest = self.data_dir.join("packs").join(&pack_id);
        if dest.exists() {
            fs::remove_dir_all(&dest)?;
        }
        copy_dir(&root, &dest)?;

        let track_id = read_track_id(&dest).unwrap_or_else(|| module_id.clone());
        let pack = InstalledPack {
            pack_id: pack_id.clone(),
            module_id: module_id.clone(),
            track_id,
            title: title.clone(),
            content_root_sha256: content_root_sha256.clone(),
            source_commit: source_commit.clone(),
            schema_version: schema_version.clone(),
            verification_status: "verified".into(),
            install_path: dest.to_string_lossy().into_owned(),
            content_version: schema_version,
        };
        self.db.upsert_pack(&pack)?;

        Ok(TrustStatus {
            pack_id,
            module_id,
            title,
            verification_status: "verified".into(),
            content_root_sha256,
            source_commit,
            trusted: true,
        })
    }

    pub fn list_installed(&self) -> Result<Vec<TrustStatus>, AppError> {
        Ok(self
            .db
            .list_packs()?
            .into_iter()
            .map(|p| TrustStatus {
                pack_id: p.pack_id,
                module_id: p.module_id,
                title: p.title,
                verification_status: p.verification_status.clone(),
                content_root_sha256: p.content_root_sha256,
                source_commit: p.source_commit,
                trusted: p.verification_status == "verified",
            })
            .collect())
    }

    pub fn list_lessons(&self, pack_id: &str) -> Result<Vec<LessonInfo>, AppError> {
        let pack = self
            .db
            .get_pack(pack_id)?
            .ok_or_else(|| AppError::NotFound(pack_id.into()))?;
        if pack.verification_status != "verified" {
            return Err(AppError::VerifyBeforeTrust(
                "pack is not trusted; refuse lesson list".into(),
            ));
        }
        let module_path = PathBuf::from(&pack.install_path).join("course_module.json");
        let module_path = if module_path.exists() {
            module_path
        } else {
            PathBuf::from(&pack.install_path)
                .join("learner")
                .join("course_module.json")
        };
        let doc: Value = serde_json::from_str(&fs::read_to_string(module_path)?)?;
        let lessons = doc
            .get("lessons")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut out = Vec::new();
        for lesson in lessons {
            out.push(LessonInfo {
                lesson_id: lesson.get("lesson_id").and_then(|v| v.as_str()).unwrap_or("").into(),
                title: lesson.get("title").and_then(|v| v.as_str()).unwrap_or("").into(),
                path: lesson.get("path").and_then(|v| v.as_str()).unwrap_or("").into(),
                week: lesson.get("week").and_then(|v| v.as_i64()),
                order: lesson.get("order").and_then(|v| v.as_i64()),
            });
        }
        out.sort_by_key(|l| l.order.unwrap_or(0));
        Ok(out)
    }

    pub fn open_lesson(&self, pack_id: &str, lesson_id: &str) -> Result<LessonContent, AppError> {
        let pack = self
            .db
            .get_pack(pack_id)?
            .ok_or_else(|| AppError::NotFound(pack_id.into()))?;
        if pack.verification_status != "verified" {
            return Err(AppError::VerifyBeforeTrust(
                "refusing to open lesson from untrusted pack".into(),
            ));
        }
        let lessons = self.list_lessons(pack_id)?;
        let lesson = lessons
            .into_iter()
            .find(|l| l.lesson_id == lesson_id)
            .ok_or_else(|| AppError::NotFound(lesson_id.into()))?;
        let base = PathBuf::from(&pack.install_path);
        let mut path = base.join(&lesson.path);
        if !path.exists() {
            path = base.join("learner").join(&lesson.path);
        }
        let markdown = fs::read_to_string(&path).map_err(|_| {
            AppError::NotFound(format!("lesson file missing: {}", lesson.path))
        })?;
        let resume = self
            .db
            .get_position(pack_id, lesson_id)?
            .map(|p| p.scroll_offset)
            .unwrap_or(0.0);
        Ok(LessonContent {
            lesson_id: lesson.lesson_id,
            title: lesson.title,
            path: lesson.path,
            markdown,
            resume_scroll_offset: resume,
        })
    }

    pub fn save_lesson_position(
        &self,
        pack_id: &str,
        lesson_id: &str,
        path: &str,
        scroll_offset: f64,
    ) -> Result<(), AppError> {
        let _ = self
            .db
            .get_pack(pack_id)?
            .ok_or_else(|| AppError::NotFound(pack_id.into()))?;
        self.db.save_position(&crate::db::LessonPosition {
            pack_id: pack_id.into(),
            lesson_id: lesson_id.into(),
            path: path.into(),
            scroll_offset,
            updated_utc: chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
        })
    }

    pub fn resume_position(&self, pack_id: &str) -> Result<Option<crate::db::LessonPosition>, AppError> {
        self.db.latest_position(pack_id)
    }
}

fn is_downgrade(existing: &str, incoming: &str) -> bool {
    // Simple lexical semver major.minor.patch compare for PR1.
    parse_semver(incoming) < parse_semver(existing)
}

fn parse_semver(v: &str) -> (u64, u64, u64) {
    let mut parts = v.split('.');
    let major = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    let minor = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    let patch = parts.next().and_then(|p| p.parse().ok()).unwrap_or(0);
    (major, minor, patch)
}

fn read_track_id(install_root: &Path) -> Option<String> {
    for candidate in [
        install_root.join("canonical_track_reference.json"),
        install_root.join("learner").join("canonical_track_reference.json"),
    ] {
        if candidate.exists() {
            if let Ok(text) = fs::read_to_string(candidate) {
                if let Ok(v) = serde_json::from_str::<Value>(&text) {
                    return v
                        .get("track_id")
                        .and_then(|x| x.as_str())
                        .map(|s| s.to_string());
                }
            }
        }
    }
    None
}

fn materialize_pack(source: &Path, work: &Path) -> Result<PathBuf, AppError> {
    if source.is_file()
        && source
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.eq_ignore_ascii_case("zip"))
            .unwrap_or(false)
    {
        let file = fs::File::open(source)?;
        let mut archive = ZipArchive::new(file)?;
        archive.extract(work)?;
        // If zip contains content at root with manifest, use work; else find subdir.
        if work.join("learner_pack_manifest.json").exists() {
            return Ok(work.to_path_buf());
        }
        return Ok(work.to_path_buf());
    }
    if source.is_dir() {
        // Accept either the build root (with learner/ + manifests) or extracted zip root.
        if source.join("learner_pack_manifest.json").exists() {
            let dest = work.join("pack");
            copy_dir(source, &dest)?;
            // Flatten learner/ contents beside manifests for a uniform install layout.
            let learner = dest.join("learner");
            if learner.is_dir() {
                for entry in WalkDir::new(&learner).into_iter().filter_map(|e| e.ok()) {
                    if entry.file_type().is_file() {
                        let rel = entry.path().strip_prefix(&learner).unwrap();
                        let target = dest.join(rel);
                        if let Some(parent) = target.parent() {
                            fs::create_dir_all(parent)?;
                        }
                        fs::copy(entry.path(), &target)?;
                    }
                }
            }
            return Ok(dest);
        }
        if source.join("course_module.json").exists() {
            let dest = work.join("pack");
            copy_dir(source, &dest)?;
            return Ok(dest);
        }
    }
    Err(AppError::VerifyBeforeTrust(format!(
        "unrecognized pack path: {}",
        source.display()
    )))
}

fn copy_dir(src: &Path, dst: &Path) -> Result<(), AppError> {
    fs::create_dir_all(dst)?;
    for entry in WalkDir::new(src).into_iter().filter_map(|e| e.ok()) {
        let path = entry.path();
        let rel = path.strip_prefix(src).unwrap();
        let target = dst.join(rel);
        if entry.file_type().is_dir() {
            fs::create_dir_all(&target)?;
        } else if entry.file_type().is_file() {
            if let Some(parent) = target.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(path, &target)?;
        }
    }
    Ok(())
}

fn sha256_file(path: &Path) -> Result<String, AppError> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 64];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

fn sha256_bytes(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

pub fn verify_learner_pack(root: &Path, verify_key: &VerifyingKey) -> Result<(bool,), AppError> {
    let manifest_path = root.join("learner_pack_manifest.json");
    if !manifest_path.exists() {
        return Err(AppError::VerifyBeforeTrust("manifest missing".into()));
    }
    let sig_path = root.join("learner_pack.signature.json");
    if !sig_path.exists() {
        return Err(AppError::UnsignedPack("signature file missing".into()));
    }

    let manifest_text = fs::read_to_string(&manifest_path)?;
    let manifest: Value = serde_json::from_str(&manifest_text)?;
    let sig_meta: SignatureMeta = serde_json::from_str(&fs::read_to_string(&sig_path)?)?;

    let schema_version = manifest
        .get("schema_version")
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0");
    check_schema_major(schema_version)?;

    let role = manifest.get("role").and_then(|v| v.as_str()).unwrap_or("");
    if role != "learner" {
        return Err(AppError::WrongRole(format!("role={role}")));
    }

    if let Some(compat) = manifest.get("compatibility") {
        check_compatibility(compat)?;
    }

    let payload = if root.join("learner_pack.manifest.canonical.json").exists() {
        fs::read(root.join("learner_pack.manifest.canonical.json"))?
    } else {
        // Fall back to file bytes of pretty/canonical manifest as stored.
        fs::read(&manifest_path)?
    };

    if sha256_bytes(&payload) != sig_meta.signed_payload_sha256 {
        return Err(AppError::TamperedContent("payload hash mismatch".into()));
    }
    if sig_meta.alg != "Ed25519" {
        return Err(AppError::BadSignature("unsupported alg".into()));
    }
    let sig_bytes = base64::Engine::decode(
        &base64::engine::general_purpose::STANDARD,
        &sig_meta.signature_b64,
    )
    .map_err(|e| AppError::BadSignature(e.to_string()))?;
    let signature = Signature::from_slice(&sig_bytes)
        .map_err(|e| AppError::BadSignature(e.to_string()))?;
    verify_key
        .verify(&payload, &signature)
        .map_err(|_| AppError::BadSignature("Ed25519 verify failed".into()))?;

    let files = manifest
        .get("files")
        .and_then(|v| v.as_array())
        .ok_or_else(|| AppError::VerifyBeforeTrust("files missing".into()))?;

    for entry in files {
        let rel = entry
            .get("path")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::TamperedContent("file path missing".into()))?;
        let expected = entry
            .get("sha256")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::TamperedContent("file hash missing".into()))?;
        let low = rel.to_lowercase();
        if INSTRUCTOR_LEAK_HINTS.iter().any(|h| low.contains(h)) {
            return Err(AppError::InstructorMaterialInLearner(rel.into()));
        }
        if PRIVATE_KEY_HINTS.iter().any(|h| low.contains(&h.to_lowercase())) {
            return Err(AppError::PrivateKeyInLearner(rel.into()));
        }
        let mut path = root.join(rel);
        if !path.exists() {
            path = root.join("learner").join(rel);
        }
        if !path.is_file() {
            return Err(AppError::TamperedContent(format!("missing {rel}")));
        }
        let digest = sha256_file(&path)?;
        if digest != expected {
            return Err(AppError::TamperedContent(format!("hash mismatch {rel}")));
        }
    }

    Ok((true,))
}

fn check_schema_major(schema_version: &str) -> Result<(), AppError> {
    let (major, _, _) = parse_semver(schema_version);
    if major != 1 {
        return Err(AppError::IncompatibleSchemaMajor(format!(
            "learner_pack_manifest {schema_version}"
        )));
    }
    Ok(())
}

fn check_compatibility(compat: &Value) -> Result<(), AppError> {
    let sv = compat
        .get("schema_version")
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0");
    check_schema_major(sv)?;
    let platform_min = compat
        .get("platform_min")
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0");
    if parse_semver(PLATFORM_VERSION) < parse_semver(platform_min) {
        return Err(AppError::PlatformTooOld(format!("need >= {platform_min}")));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::keyring_store::decode_hex_key;
    use std::process::Command;

    fn repo_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()
            .unwrap()
    }

    fn verify_key_bytes() -> Vec<u8> {
        fs::read(repo_root().join("contracts/fixtures/keys/TEST_ONLY_ed25519_public.key")).unwrap()
    }

    fn ensure_sample_pack() -> PathBuf {
        let out = repo_root().join("pack_out");
        if !out.join("learner_pack_manifest.json").exists() {
            let status = Command::new(repo_root().join(".venv/bin/course-compiler"))
                .args(["compile", "DIGITAL_CONFIDENCE", "--out"])
                .arg(&out)
                .env("SOURCE_DATE_EPOCH", "1700000000")
                .current_dir(repo_root())
                .status();
            if status.is_err() || !status.unwrap().success() {
                // Fallback: PYTHONPATH
                let status2 = Command::new(repo_root().join(".venv/bin/python3"))
                    .args([
                        "-m",
                        "course_compiler.cli",
                        "compile",
                        "DIGITAL_CONFIDENCE",
                        "--out",
                    ])
                    .arg(&out)
                    .env("SOURCE_DATE_EPOCH", "1700000000")
                    .env(
                        "PYTHONPATH",
                        repo_root().join("tools/course_compiler"),
                    )
                    .current_dir(repo_root())
                    .status()
                    .expect("compile pack");
                assert!(status2.success(), "compiler failed");
            }
        }
        out
    }

    #[test]
    fn install_verify_persist_restart() {
        let pack_src = ensure_sample_pack();
        let dir = tempfile::tempdir().unwrap();
        let key = decode_hex_key(&"11".repeat(32)).unwrap();
        let svc = PackService::new(dir.path().to_path_buf(), &verify_key_bytes(), key).unwrap();
        let trust = svc.install_pack(&pack_src).unwrap();
        assert!(trust.trusted);
        assert_eq!(trust.module_id, "DIGITAL_CONFIDENCE");
        assert_eq!(trust.verification_status, "verified");

        let lessons = svc.list_lessons(&trust.pack_id).unwrap();
        assert!(!lessons.is_empty(), "expected lessons from real module");
        let first = &lessons[0];
        let content = svc.open_lesson(&trust.pack_id, &first.lesson_id).unwrap();
        assert!(!content.markdown.is_empty());
        svc.save_lesson_position(&trust.pack_id, &first.lesson_id, &first.path, 42.0)
            .unwrap();

        // restart simulation
        drop(svc);
        let svc2 = PackService::new(dir.path().to_path_buf(), &verify_key_bytes(), key).unwrap();
        let pos = svc2.resume_position(&trust.pack_id).unwrap().unwrap();
        assert!((pos.scroll_offset - 42.0).abs() < f64::EPSILON);
        assert_eq!(pos.lesson_id, first.lesson_id);
    }

    #[test]
    fn rejects_unsigned_and_wrong_role() {
        let pack_src = ensure_sample_pack();
        let dir = tempfile::tempdir().unwrap();
        let work = dir.path().join("unsigned");
        copy_dir(&pack_src, &work).unwrap();
        // flatten like install does
        let learner = work.join("learner");
        if learner.is_dir() {
            for entry in WalkDir::new(&learner).into_iter().filter_map(|e| e.ok()) {
                if entry.file_type().is_file() {
                    let rel = entry.path().strip_prefix(&learner).unwrap();
                    let target = work.join(rel);
                    if let Some(parent) = target.parent() {
                        fs::create_dir_all(parent).unwrap();
                    }
                    fs::copy(entry.path(), &target).unwrap();
                }
            }
        }
        fs::remove_file(work.join("learner_pack.signature.json")).unwrap();
        let key_bytes = verify_key_bytes();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&key_bytes);
        let vk = VerifyingKey::from_bytes(&arr).unwrap();
        let err = verify_learner_pack(&work, &vk).unwrap_err();
        assert!(matches!(err, AppError::UnsignedPack(_)));

        // wrong role
        let work2 = dir.path().join("wrong_role");
        copy_dir(&pack_src, &work2).unwrap();
        let learner = work2.join("learner");
        if learner.is_dir() {
            for entry in WalkDir::new(&learner).into_iter().filter_map(|e| e.ok()) {
                if entry.file_type().is_file() {
                    let rel = entry.path().strip_prefix(&learner).unwrap();
                    let target = work2.join(rel);
                    if let Some(parent) = target.parent() {
                        fs::create_dir_all(parent).unwrap();
                    }
                    fs::copy(entry.path(), &target).unwrap();
                }
            }
        }
        let mut manifest: Value =
            serde_json::from_str(&fs::read_to_string(work2.join("learner_pack_manifest.json")).unwrap())
                .unwrap();
        manifest["role"] = Value::String("instructor".into());
        fs::write(
            work2.join("learner_pack_manifest.json"),
            serde_json::to_string_pretty(&manifest).unwrap(),
        )
        .unwrap();
        // Also update canonical payload so signature path still fails closed on role before or after
        // For this test we call verify which checks role before signature if we reorder —
        // our implementation checks role before signature. Good.
        let err2 = verify_learner_pack(&work2, &vk).unwrap_err();
        assert!(matches!(err2, AppError::WrongRole(_)));
    }

    #[test]
    fn rejects_tampered_content() {
        let pack_src = ensure_sample_pack();
        let dir = tempfile::tempdir().unwrap();
        let work = dir.path().join("tampered");
        copy_dir(&pack_src, &work).unwrap();

        // Tamper a file that is actually listed in the signed manifest hashes.
        let manifest: Value = serde_json::from_str(
            &fs::read_to_string(work.join("learner_pack_manifest.json")).unwrap(),
        )
        .unwrap();
        let rel = manifest["files"]
            .as_array()
            .unwrap()
            .iter()
            .find_map(|e| {
                let p = e.get("path")?.as_str()?;
                if p.ends_with(".md") {
                    Some(p.to_string())
                } else {
                    None
                }
            })
            .expect("expected a markdown file in learner manifest");

        let candidates = [work.join("learner").join(&rel), work.join(&rel)];
        let target = candidates
            .into_iter()
            .find(|p| p.is_file())
            .expect("manifest path must exist on disk");
        let mut bytes = fs::read(&target).unwrap();
        bytes[0] ^= 0x01;
        fs::write(&target, bytes).unwrap();

        let key_bytes = verify_key_bytes();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&key_bytes);
        let vk = VerifyingKey::from_bytes(&arr).unwrap();
        let err = verify_learner_pack(&work, &vk).unwrap_err();
        assert!(matches!(err, AppError::TamperedContent(_)));
    }
}
