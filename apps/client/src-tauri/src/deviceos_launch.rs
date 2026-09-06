//! Device OS ↔ Learning OS native launch protocol (`gunnchos.learning_os.ipc.v1`).
//!
//! Parses Device OS CLI options, validates the file-drop request, stores a one-shot
//! navigation intent, and writes ACK/NACK under the IPC directory.

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime};
use std::{env, thread};

pub const PROTOCOL_ID: &str = "gunnchos.learning_os.ipc.v1";
pub const BUNDLE_ID: &str = "com.gunnchos.waike.learning";
pub const MESSAGE_LAUNCH_CONTEXT: &str = "launch_context";
pub const MESSAGE_ACK: &str = "ack";
pub const MESSAGE_NACK: &str = "nack";
pub const DEEP_LINK_SCHEME: &str = "waike";

const MAX_REQUEST_BYTES: u64 = 64 * 1024;
const REQUEST_WAIT: Duration = Duration::from_secs(8);
const STALE_REQUEST: Duration = Duration::from_secs(120);

const ALLOWED_CONTEXT_KEYS: &[&str] = &[
    "profile",
    "mode",
    "device_role",
    "platform_role",
    "shell_form_factor",
    "registry_id",
    "bundle_id",
    "sdk_app_id",
    "runtime_id",
    "course_id",
    "section_id",
    "activity_id",
    "sync_cursor",
    "revision",
];

const SECRET_CONTEXT_KEYS: &[&str] = &[
    "password",
    "passwords",
    "private_key",
    "private_keys",
    "session_token",
    "session_tokens",
    "db_key",
    "db_keys",
    "lti_private_key",
    "api_key",
    "secret",
    "bearer",
    "authorization",
    "auth",
    "jwt",
    "token",
    "answer_key",
    "waike_dev_db_key",
    "instructor_key",
];

const ALLOWED_DEEP_LINK_KINDS: &[&str] = &[
    "learn",
    "section",
    "quiz",
    "assignment",
    "sync",
    "device",
];

#[derive(Debug, Clone, Default)]
pub struct DeviceOsCliArgs {
    pub bundle_id: Option<String>,
    pub deep_link: Option<String>,
    pub ipc_dir: Option<String>,
    pub request_id: Option<String>,
    pub headless_ui: bool,
}

impl DeviceOsCliArgs {
    pub fn is_present(&self) -> bool {
        self.ipc_dir.is_some() || self.request_id.is_some() || self.bundle_id.is_some()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeepLinkIntent {
    pub uri: String,
    pub canonical: String,
    pub kind: String,
    pub path: String,
    pub segments: Vec<String>,
    pub valid: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceOsLaunchContext {
    pub protocol: String,
    pub request_id: String,
    pub bundle_id: String,
    pub deep_link: DeepLinkIntent,
    pub context: Map<String, Value>,
    pub app_version: String,
    pub consumed: bool,
}

#[derive(Debug, Clone)]
pub struct PreparedLaunch {
    pub ipc_dir: PathBuf,
    pub request_id: String,
    #[allow(dead_code)]
    pub cli_deep_link: Option<String>,
    pub headless_ui: bool,
    pub intent: DeviceOsLaunchContext,
}

#[derive(Debug, Clone)]
pub enum LaunchPrepError {
    Nack {
        #[allow(dead_code)]
        request_id: String,
        #[allow(dead_code)]
        ipc_dir: Option<PathBuf>,
        reason: String,
    },
    Fatal(String),
}

pub fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

pub fn parse_cli_args<I, S>(args: I) -> DeviceOsCliArgs
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut out = DeviceOsCliArgs::default();
    let mut iter = args.into_iter().map(|s| s.as_ref().to_string());
    // Skip argv[0]
    let _ = iter.next();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--bundle-id" => out.bundle_id = iter.next(),
            "--deep-link" => out.deep_link = iter.next(),
            "--ipc-dir" => out.ipc_dir = iter.next(),
            "--request-id" => out.request_id = iter.next(),
            "--device-os-protocol" => {
                let _ = iter.next();
            }
            "--ci-headless-ui" => out.headless_ui = true,
            other if other.starts_with("--bundle-id=") => {
                out.bundle_id = Some(other[12..].to_string());
            }
            other if other.starts_with("--deep-link=") => {
                out.deep_link = Some(other[12..].to_string());
            }
            other if other.starts_with("--ipc-dir=") => {
                out.ipc_dir = Some(other[10..].to_string());
            }
            other if other.starts_with("--request-id=") => {
                out.request_id = Some(other[13..].to_string());
            }
            _ => {
                // Ignore unknown Tauri/system args; never trust as context.
            }
        }
    }
    if env_truthy("WAIKE_CI_HEADLESS_UI") || env_truthy("CI_HEADLESS_UI") {
        out.headless_ui = true;
    }
    if out.request_id.is_none() {
        if let Ok(v) = env::var("LEARNING_OS_REQUEST_ID") {
            if !v.is_empty() {
                out.request_id = Some(v);
            }
        }
    }
    out
}

fn env_truthy(name: &str) -> bool {
    matches!(
        env::var(name).ok().as_deref(),
        Some("1") | Some("true") | Some("TRUE") | Some("yes") | Some("YES")
    )
}

pub fn prepare_deviceos_launch(cli: &DeviceOsCliArgs) -> Result<Option<PreparedLaunch>, LaunchPrepError> {
    if !cli.is_present() {
        return Ok(None);
    }
    let request_id = cli
        .request_id
        .clone()
        .ok_or_else(|| LaunchPrepError::Fatal("missing_request_id".into()))?;
    if !is_safe_request_id(&request_id) {
        return Err(LaunchPrepError::Fatal("bad_request_id".into()));
    }
    let ipc_raw = cli
        .ipc_dir
        .clone()
        .ok_or_else(|| LaunchPrepError::Fatal("missing_ipc_dir".into()))?;
    let ipc_dir = match canonicalize_ipc_dir(&ipc_raw) {
        Ok(p) => p,
        Err(reason) => {
            return Err(LaunchPrepError::Nack {
                request_id: request_id.clone(),
                ipc_dir: None,
                reason,
            });
        }
    };

    if let Some(bid) = &cli.bundle_id {
        if bid != BUNDLE_ID {
            let _ = write_nack(&ipc_dir, &request_id, "wrong_bundle_id");
            return Err(LaunchPrepError::Nack {
                request_id,
                ipc_dir: Some(ipc_dir),
                reason: "wrong_bundle_id".into(),
            });
        }
    }

    let req_path = ipc_dir.join(format!("request-{request_id}.json"));
    if let Err(reason) = wait_for_request(&req_path) {
        let _ = write_nack(&ipc_dir, &request_id, &reason);
        return Err(LaunchPrepError::Nack {
            request_id,
            ipc_dir: Some(ipc_dir),
            reason,
        });
    }

    // Idempotency: prior ACK already present → do not re-queue navigation.
    let ack_path = ipc_dir.join(format!("ack-{request_id}.json"));
    if ack_path.is_file() {
        if let Ok(existing) = read_json_limited(&ack_path) {
            if existing.get("message_type").and_then(|v| v.as_str()) == Some(MESSAGE_ACK)
                && existing.get("request_id").and_then(|v| v.as_str()) == Some(request_id.as_str())
                && existing.get("protocol").and_then(|v| v.as_str()) == Some(PROTOCOL_ID)
            {
                let intent = DeviceOsLaunchContext {
                    protocol: PROTOCOL_ID.to_string(),
                    request_id: request_id.clone(),
                    bundle_id: BUNDLE_ID.to_string(),
                    deep_link: DeepLinkIntent {
                        uri: cli.deep_link.clone().unwrap_or_default(),
                        canonical: cli.deep_link.clone().unwrap_or_default(),
                        kind: String::new(),
                        path: String::new(),
                        segments: vec![],
                        valid: true,
                    },
                    context: Map::new(),
                    app_version: app_version(),
                    consumed: true,
                };
                return Ok(Some(PreparedLaunch {
                    ipc_dir,
                    request_id,
                    cli_deep_link: cli.deep_link.clone(),
                    headless_ui: cli.headless_ui,
                    intent,
                }));
            }
        }
    }

    match validate_request_file(&req_path, &request_id, cli.deep_link.as_deref()) {
        Ok(intent) => Ok(Some(PreparedLaunch {
            ipc_dir,
            request_id,
            cli_deep_link: cli.deep_link.clone(),
            headless_ui: cli.headless_ui,
            intent,
        })),
        Err(reason) => {
            let _ = write_nack(&ipc_dir, &request_id, &reason);
            Err(LaunchPrepError::Nack {
                request_id,
                ipc_dir: Some(ipc_dir),
                reason,
            })
        }
    }
}

pub fn write_success_ack(prepared: &PreparedLaunch) -> Result<(), String> {
    let payload = json!({
        "protocol": PROTOCOL_ID,
        "message_type": MESSAGE_ACK,
        "request_id": prepared.request_id,
        "status": "ok",
        "app_version": prepared.intent.app_version,
        "bundle_id": BUNDLE_ID,
        "deep_link": prepared.intent.deep_link.canonical,
    });
    write_json_atomic(
        &prepared.ipc_dir.join(format!("ack-{}.json", prepared.request_id)),
        &payload,
    )
}

pub fn write_nack(ipc_dir: &Path, request_id: &str, reason: &str) -> Result<(), String> {
    let payload = json!({
        "protocol": PROTOCOL_ID,
        "message_type": MESSAGE_NACK,
        "request_id": request_id,
        "reason": reason,
    });
    write_json_atomic(&ipc_dir.join(format!("ack-{request_id}.json")), &payload)
}

fn is_safe_request_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn canonicalize_ipc_dir(raw: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err("ipc_dir_not_absolute".into());
    }
    if raw.contains("..") {
        return Err("ipc_dir_traversal".into());
    }
    fs::create_dir_all(&path).map_err(|e| format!("ipc_dir_create:{e}"))?;
    let canon = path
        .canonicalize()
        .map_err(|e| format!("ipc_dir_canonicalize:{e}"))?;
    // Reject if the canonical path somehow escaped (e.g. symlink to unexpected root).
    // Allow temp dirs and workspace CI paths; require the leaf still exists as a dir.
    if !canon.is_dir() {
        return Err("ipc_dir_not_directory".into());
    }
    // Symlink escape: ensure request/ack joins stay under canon via path containment later.
    Ok(canon)
}

fn wait_for_request(path: &Path) -> Result<(), String> {
    let deadline = Instant::now() + REQUEST_WAIT;
    while Instant::now() < deadline {
        if path.is_file() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(20));
    }
    Err("missing_request_file".into())
}

fn validate_request_file(
    path: &Path,
    expected_request_id: &str,
    cli_deep_link: Option<&str>,
) -> Result<DeviceOsLaunchContext, String> {
    // Path must stay under parent (no symlink escape of the request file itself).
    let parent = path
        .parent()
        .ok_or_else(|| "bad_request_path".to_string())?;
    let parent_canon = parent
        .canonicalize()
        .map_err(|e| format!("request_parent_canonicalize:{e}"))?;
    let file_canon = path
        .canonicalize()
        .map_err(|e| format!("request_canonicalize:{e}"))?;
    if !file_canon.starts_with(&parent_canon) {
        return Err("request_path_escape".into());
    }

    let meta = fs::metadata(&file_canon).map_err(|e| format!("request_stat:{e}"))?;
    if meta.len() > MAX_REQUEST_BYTES {
        return Err("request_too_large".into());
    }
    if let Ok(modified) = meta.modified() {
        if let Ok(age) = SystemTime::now().duration_since(modified) {
            if age > STALE_REQUEST {
                return Err("stale_request".into());
            }
        }
    }

    let value = read_json_limited(&file_canon)?;
    let obj = value
        .as_object()
        .ok_or_else(|| "bad_payload".to_string())?;

    if obj.get("protocol").and_then(|v| v.as_str()) != Some(PROTOCOL_ID) {
        return Err("wrong_protocol_version".into());
    }
    if obj.get("message_type").and_then(|v| v.as_str()) != Some(MESSAGE_LAUNCH_CONTEXT) {
        return Err("bad_message_type".into());
    }
    let rid = obj
        .get("request_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "missing_request_id".to_string())?;
    if rid != expected_request_id {
        return Err("request_id_mismatch".into());
    }
    let bundle = obj
        .get("bundle_id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "missing_bundle_id".to_string())?;
    if bundle != BUNDLE_ID {
        return Err("wrong_bundle_id".into());
    }

    let deep_link_val = obj.get("deep_link");
    let parsed = match deep_link_val {
        None | Some(Value::Null) => parse_deep_link(None)?,
        Some(Value::Object(m)) => {
            let uri = m
                .get("canonical")
                .or_else(|| m.get("uri"))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            let parsed = parse_deep_link(uri.as_deref())?;
            if let Some(valid) = m.get("valid").and_then(|v| v.as_bool()) {
                if !valid {
                    return Err(m
                        .get("reason")
                        .and_then(|v| v.as_str())
                        .unwrap_or("deep_link_rejected")
                        .to_string());
                }
            }
            if !parsed.valid {
                return Err("deep_link_rejected".into());
            }
            // Prefer already-normalized fields when present and consistent.
            if let Some(kind) = m.get("kind").and_then(|v| v.as_str()) {
                if kind != parsed.kind {
                    return Err("deep_link_kind_mismatch".into());
                }
            }
            parsed
        }
        Some(Value::String(s)) => parse_deep_link(Some(s))?,
        Some(_) => return Err("bad_deep_link".into()),
    };
    if !parsed.valid {
        return Err("deep_link_rejected".into());
    }

    if let Some(cli) = cli_deep_link {
        let cli_parsed = parse_deep_link(Some(cli))?;
        if !cli_parsed.valid {
            return Err("cli_deep_link_rejected".into());
        }
        if cli_parsed.canonical != parsed.canonical {
            return Err("deep_link_mismatch".into());
        }
    }

    let context_val = obj.get("context").cloned().unwrap_or_else(|| json!({}));
    let context = context_val
        .as_object()
        .ok_or_else(|| "bad_context".to_string())?;
    let allowed: HashSet<&str> = ALLOWED_CONTEXT_KEYS.iter().copied().collect();
    let secrets: HashSet<&str> = SECRET_CONTEXT_KEYS.iter().copied().collect();
    let mut clean = Map::new();
    for (k, v) in context {
        let key_l = k.to_ascii_lowercase();
        if secrets.contains(key_l.as_str()) {
            return Err(format!("secret_context_field:{k}"));
        }
        if !allowed.contains(k.as_str()) {
            return Err(format!("unknown_context_field:{k}"));
        }
        // Reject arbitrary filesystem paths if a string looks like an absolute path key misuse.
        if matches!(k.as_str(), "course_id" | "section_id" | "activity_id" | "sync_cursor") {
            if let Some(s) = v.as_str() {
                if s.contains('\0') || s.contains("..") || s.starts_with('/') || s.contains('\\') {
                    return Err(format!("unsafe_context_value:{k}"));
                }
            }
        }
        clean.insert(k.clone(), v.clone());
    }

    Ok(DeviceOsLaunchContext {
        protocol: PROTOCOL_ID.to_string(),
        request_id: expected_request_id.to_string(),
        bundle_id: BUNDLE_ID.to_string(),
        deep_link: parsed,
        context: clean,
        app_version: app_version(),
        consumed: false,
    })
}

fn read_json_limited(path: &Path) -> Result<Value, String> {
    let file = File::open(path).map_err(|e| format!("request_open:{e}"))?;
    let mut buf = Vec::new();
    file.take(MAX_REQUEST_BYTES + 1)
        .read_to_end(&mut buf)
        .map_err(|e| format!("request_read:{e}"))?;
    if buf.len() as u64 > MAX_REQUEST_BYTES {
        return Err("request_too_large".into());
    }
    serde_json::from_slice(&buf).map_err(|_| "bad_payload".to_string())
}

fn write_json_atomic(path: &Path, value: &Value) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "ack_parent_missing".to_string())?;
    fs::create_dir_all(parent).map_err(|e| format!("ack_mkdir:{e}"))?;
    let tmp = parent.join(format!(
        ".{}.tmp",
        path.file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("ack.json")
    ));
    {
        let mut opts = OpenOptions::new();
        opts.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            opts.mode(0o600);
        }
        let mut f = opts.open(&tmp).map_err(|e| format!("ack_tmp_open:{e}"))?;
        let body = serde_json::to_vec_pretty(value).map_err(|e| format!("ack_serialize:{e}"))?;
        f.write_all(&body).map_err(|e| format!("ack_write:{e}"))?;
        f.write_all(b"\n").map_err(|e| format!("ack_write:{e}"))?;
        f.sync_all().ok();
    }
    fs::rename(&tmp, path).map_err(|e| format!("ack_rename:{e}"))?;
    Ok(())
}

pub fn parse_deep_link(uri: Option<&str>) -> Result<DeepLinkIntent, String> {
    let Some(raw) = uri.map(str::trim).filter(|s| !s.is_empty()) else {
        return Ok(DeepLinkIntent {
            uri: String::new(),
            canonical: format!("{DEEP_LINK_SCHEME}://learn/home"),
            kind: "learn".into(),
            path: "home".into(),
            segments: vec!["home".into()],
            valid: true,
        });
    };
    if raw.contains('\0') {
        return Err("nul_rejected".into());
    }
    if raw.contains('\\') {
        return Err("backslash_rejected".into());
    }
    let prefix = format!("{DEEP_LINK_SCHEME}://");
    if !raw.to_ascii_lowercase().starts_with(&prefix) {
        return Err("scheme_or_kind_rejected".into());
    }
    let rest = &raw[prefix.len()..];
    if rest.is_empty() {
        return Err("scheme_or_kind_rejected".into());
    }
    let parts: Vec<&str> = rest.split('/').collect();
    let kind_decoded = decode_once(parts[0])?;
    let kind = kind_decoded.to_ascii_lowercase();
    if !kind.chars().all(|c| c.is_ascii_alphabetic())
        || !ALLOWED_DEEP_LINK_KINDS.contains(&kind.as_str())
    {
        return Err("kind_rejected".into());
    }
    let mut segments = Vec::new();
    for seg in &parts[1..] {
        if seg.is_empty() {
            continue;
        }
        let decoded = decode_once(seg)?;
        if decoded.contains('\\') || decoded.contains('/') {
            return Err("path_traversal_rejected".into());
        }
        if decoded == "." || decoded == ".." || decoded.contains("..") {
            return Err("path_traversal_rejected".into());
        }
        if !decoded
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        {
            return Err("path_segment_rejected".into());
        }
        segments.push(decoded);
    }
    let path = segments.join("/");
    let canonical = if path.is_empty() {
        format!("{DEEP_LINK_SCHEME}://{kind}")
    } else {
        format!("{DEEP_LINK_SCHEME}://{kind}/{path}")
    };
    Ok(DeepLinkIntent {
        uri: raw.to_string(),
        canonical,
        kind,
        path,
        segments,
        valid: true,
    })
}

fn decode_once(segment: &str) -> Result<String, String> {
    if segment.contains('%') {
        // Reject double-encoding / encoded percent / invalid sequences.
        let bytes = segment.as_bytes();
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i] != b'%' {
                i += 1;
                continue;
            }
            if i + 2 >= bytes.len() {
                return Err("encoding_rejected".into());
            }
            let h1 = bytes[i + 1];
            let h2 = bytes[i + 2];
            if !h1.is_ascii_hexdigit() || !h2.is_ascii_hexdigit() {
                return Err("encoding_rejected".into());
            }
            if h1.eq_ignore_ascii_case(&b'2') && h2.eq_ignore_ascii_case(&b'5') {
                return Err("encoding_rejected".into());
            }
            i += 3;
        }
    }
    let decoded = percent_decode(segment)?;
    if decoded.contains('\0') || decoded.chars().any(|c| (c as u32) < 32) {
        return Err("encoding_rejected".into());
    }
    Ok(decoded)
}

fn percent_decode(input: &str) -> Result<String, String> {
    let bytes = input.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            if i + 2 >= bytes.len() {
                return Err("encoding_rejected".into());
            }
            let h = std::str::from_utf8(&bytes[i + 1..i + 3]).map_err(|_| "encoding_rejected")?;
            let v = u8::from_str_radix(h, 16).map_err(|_| "encoding_rejected")?;
            out.push(v);
            i += 3;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8(out).map_err(|_| "encoding_rejected".into())
}

/// Map a consumed deep-link kind into a coarse UI mode token (auth still required).
#[allow(dead_code)]
pub fn navigation_mode_for_kind(kind: &str) -> Option<&'static str> {
    match kind {
        "learn" => Some("home"),
        "section" => Some("home"),
        "quiz" | "assignment" => Some("assignments"),
        "sync" => Some("home"),
        "device" => Some("interop"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn write_req(dir: &Path, rid: &str, body: &Value) {
        fs::create_dir_all(dir).unwrap();
        fs::write(
            dir.join(format!("request-{rid}.json")),
            serde_json::to_vec_pretty(body).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn parses_cli_deviceos_flags_only() {
        let cli = parse_cli_args([
            "waike-learning-client",
            "--bundle-id",
            BUNDLE_ID,
            "--deep-link",
            "waike://learn/home",
            "--ipc-dir",
            "/tmp/ipc",
            "--request-id",
            "abc-123",
            "--unknown-flag",
            "nope",
        ]);
        assert_eq!(cli.bundle_id.as_deref(), Some(BUNDLE_ID));
        assert_eq!(cli.deep_link.as_deref(), Some("waike://learn/home"));
        assert_eq!(cli.ipc_dir.as_deref(), Some("/tmp/ipc"));
        assert_eq!(cli.request_id.as_deref(), Some("abc-123"));
    }

    #[test]
    fn deep_link_rejects_traversal_and_encoding() {
        for bad in [
            "waike://learn/%2e%2e/etc",
            "waike://learn/%252e%252e/x",
            "waike://learn/foo%00bar",
            "https://evil.example/x",
            "waike://admin/secret",
            "waike://learn/foo\\bar",
        ] {
            assert!(parse_deep_link(Some(bad)).is_err(), "{bad}");
        }
        assert!(parse_deep_link(Some("waike://section/sec-1")).is_ok());
    }

    #[test]
    fn validates_happy_path_and_mismatch() {
        let dir = tempfile::tempdir().unwrap();
        let rid = "req-happy-1";
        let body = json!({
            "protocol": PROTOCOL_ID,
            "message_type": MESSAGE_LAUNCH_CONTEXT,
            "request_id": rid,
            "bundle_id": BUNDLE_ID,
            "deep_link": {
                "uri": "waike://learn/home",
                "canonical": "waike://learn/home",
                "valid": true,
                "kind": "learn",
                "path": "home"
            },
            "context": {"profile": "student", "mode": "School", "bundle_id": BUNDLE_ID}
        });
        write_req(dir.path(), rid, &body);
        let intent = validate_request_file(
            &dir.path().join(format!("request-{rid}.json")),
            rid,
            Some("waike://learn/home"),
        )
        .unwrap();
        assert_eq!(intent.deep_link.kind, "learn");

        let err = validate_request_file(
            &dir.path().join(format!("request-{rid}.json")),
            rid,
            Some("waike://section/other"),
        )
        .unwrap_err();
        assert_eq!(err, "deep_link_mismatch");
    }

    #[test]
    fn rejects_secret_and_unknown_context() {
        let dir = tempfile::tempdir().unwrap();
        let rid = "req-secret";
        let body = json!({
            "protocol": PROTOCOL_ID,
            "message_type": MESSAGE_LAUNCH_CONTEXT,
            "request_id": rid,
            "bundle_id": BUNDLE_ID,
            "deep_link": {"canonical": "waike://learn/home", "valid": true, "kind": "learn", "path": "home"},
            "context": {"password": "x"}
        });
        write_req(dir.path(), rid, &body);
        let err = validate_request_file(&dir.path().join(format!("request-{rid}.json")), rid, None)
            .unwrap_err();
        assert!(err.starts_with("secret_context_field:"));

        let rid2 = "req-unknown";
        let body2 = json!({
            "protocol": PROTOCOL_ID,
            "message_type": MESSAGE_LAUNCH_CONTEXT,
            "request_id": rid2,
            "bundle_id": BUNDLE_ID,
            "deep_link": {"canonical": "waike://learn/home", "valid": true, "kind": "learn", "path": "home"},
            "context": {"evil_path": "/etc/passwd"}
        });
        write_req(dir.path(), rid2, &body2);
        let err2 =
            validate_request_file(&dir.path().join(format!("request-{rid2}.json")), rid2, None)
                .unwrap_err();
        assert!(err2.starts_with("unknown_context_field:"));
    }

    #[test]
    fn rejects_wrong_protocol_and_bundle() {
        let dir = tempfile::tempdir().unwrap();
        let rid = "req-proto";
        write_req(
            dir.path(),
            rid,
            &json!({
                "protocol": "nope",
                "message_type": MESSAGE_LAUNCH_CONTEXT,
                "request_id": rid,
                "bundle_id": BUNDLE_ID,
                "deep_link": {"canonical": "waike://learn/home", "valid": true, "kind": "learn", "path": "home"},
                "context": {}
            }),
        );
        assert_eq!(
            validate_request_file(&dir.path().join(format!("request-{rid}.json")), rid, None)
                .unwrap_err(),
            "wrong_protocol_version"
        );
    }

    #[test]
    fn ack_atomic_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let prepared = PreparedLaunch {
            ipc_dir: dir.path().to_path_buf(),
            request_id: "ack-1".into(),
            cli_deep_link: None,
            headless_ui: true,
            intent: DeviceOsLaunchContext {
                protocol: PROTOCOL_ID.into(),
                request_id: "ack-1".into(),
                bundle_id: BUNDLE_ID.into(),
                deep_link: parse_deep_link(Some("waike://learn/home")).unwrap(),
                context: Map::new(),
                app_version: "0.1.0".into(),
                consumed: false,
            },
        };
        write_success_ack(&prepared).unwrap();
        let ack: Value = serde_json::from_str(
            &fs::read_to_string(dir.path().join("ack-ack-1.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(ack["message_type"], MESSAGE_ACK);
        assert_eq!(ack["bundle_id"], BUNDLE_ID);
        assert_eq!(ack["status"], "ok");
        let _ = UNIX_EPOCH; // silence unused in some rustc
        let _ = SystemTime::now();
    }
}
