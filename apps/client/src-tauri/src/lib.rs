mod db;
mod error;
mod keyring_store;
mod offline;
#[cfg(test)]
mod offline_tests;
mod pack;

use chrono::Utc;
use error::{ui_code, AppError};
use keyring_store::{resolve_db_key, KeySource};
use offline::{CachedLease, OfflineState, SyncCounts, SyncOutboxItem};
use pack::{LessonContent, LessonInfo, PackService, TrustStatus};
use serde::Serialize;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::State;

pub struct AppState {
    pub service: Mutex<PackService>,
    pub key_source: KeySource,
}

#[derive(Serialize)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl From<AppError> for CommandError {
    fn from(value: AppError) -> Self {
        Self {
            code: ui_code(&value).to_string(),
            message: value.to_string(),
        }
    }
}

fn default_data_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("waike-learning-os")
}

fn load_verify_key() -> Result<Vec<u8>, AppError> {
    // Prefer bundled fixture relative to executable / resource; fall back to repo path in dev.
    let candidates = [
        PathBuf::from("contracts/fixtures/keys/TEST_ONLY_ed25519_public.key"),
        PathBuf::from("../../contracts/fixtures/keys/TEST_ONLY_ed25519_public.key"),
        PathBuf::from("../../../contracts/fixtures/keys/TEST_ONLY_ed25519_public.key"),
        default_data_dir().join("TEST_ONLY_ed25519_public.key"),
    ];
    for c in candidates {
        if c.exists() {
            return Ok(fs::read(c)?);
        }
    }
    // Absolute workspace hint for local `cargo test` / `tauri dev`
    let manifest_related = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../contracts/fixtures/keys/TEST_ONLY_ed25519_public.key");
    if manifest_related.exists() {
        return Ok(fs::read(manifest_related)?);
    }
    Err(AppError::Key(
        "TEST_ONLY verify key not found; place public key under contracts/fixtures/keys".into(),
    ))
}

#[tauri::command]
fn get_key_source(state: State<'_, AppState>) -> String {
    match state.key_source {
        KeySource::Keyring => "keyring".into(),
        KeySource::DevFallback => "dev_fallback".into(),
    }
}

#[tauri::command]
fn list_installed_packs(state: State<'_, AppState>) -> Result<Vec<TrustStatus>, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.list_installed()?)
}

#[tauri::command]
fn install_learner_pack(
    state: State<'_, AppState>,
    path: String,
) -> Result<TrustStatus, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.install_pack(PathBuf::from(path).as_path())?)
}

#[tauri::command]
fn get_trust_status(
    state: State<'_, AppState>,
    pack_id: String,
) -> Result<Option<TrustStatus>, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc
        .list_installed()?
        .into_iter()
        .find(|p| p.pack_id == pack_id))
}

#[tauri::command]
fn list_lessons(
    state: State<'_, AppState>,
    pack_id: String,
) -> Result<Vec<LessonInfo>, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.list_lessons(&pack_id)?)
}

#[tauri::command]
fn open_lesson(
    state: State<'_, AppState>,
    pack_id: String,
    lesson_id: String,
) -> Result<LessonContent, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.open_lesson(&pack_id, &lesson_id)?)
}

#[tauri::command]
fn save_lesson_position(
    state: State<'_, AppState>,
    pack_id: String,
    lesson_id: String,
    path: String,
    scroll_offset: f64,
) -> Result<(), CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.save_lesson_position(&pack_id, &lesson_id, &path, scroll_offset)?)
}

#[tauri::command]
fn get_resume_position(
    state: State<'_, AppState>,
    pack_id: String,
) -> Result<Option<crate::db::LessonPosition>, CommandError> {
    let svc = state.service.lock().map_err(|e| AppError::Db(e.to_string()))?;
    Ok(svc.resume_position(&pack_id)?)
}

// --- Gate A offline sync commands -------------------------------------------
//
// Every command takes typed values. There is no command that accepts SQL, a table
// name, or a column name, so the webview cannot reach past this surface.

macro_rules! with_db {
    ($state:expr, $db:ident, $body:expr) => {{
        let svc = $state
            .service
            .lock()
            .map_err(|e| AppError::Db(e.to_string()))?;
        let $db = &svc.db;
        let out: Result<_, AppError> = $body;
        out.map_err(CommandError::from)
    }};
}

#[tauri::command]
fn sync_cache_lease(
    state: State<'_, AppState>,
    lease: CachedLease,
    cached_at: String,
) -> Result<(), CommandError> {
    with_db!(state, db, db.cache_lease(&lease, &cached_at))
}

#[tauri::command]
fn sync_get_lease(
    state: State<'_, AppState>,
    section_id: String,
) -> Result<Option<CachedLease>, CommandError> {
    with_db!(state, db, db.get_section_lease(&section_id))
}

#[tauri::command]
fn sync_list_leases(state: State<'_, AppState>) -> Result<Vec<CachedLease>, CommandError> {
    with_db!(state, db, db.list_leases())
}

#[tauri::command]
fn sync_mark_lease_revoked(
    state: State<'_, AppState>,
    lease_id: String,
    reason: String,
) -> Result<(), CommandError> {
    with_db!(state, db, db.mark_lease_revoked(&lease_id, &reason))
}

#[tauri::command]
fn sync_mark_lease_expired(
    state: State<'_, AppState>,
    lease_id: String,
    expired_at: String,
) -> Result<(), CommandError> {
    with_db!(state, db, db.mark_lease_expired(&lease_id, &expired_at))
}

#[tauri::command]
fn sync_enqueue_mutation(
    state: State<'_, AppState>,
    item: SyncOutboxItem,
) -> Result<(), CommandError> {
    with_db!(state, db, db.enqueue_sync_mutation(&item))
}

#[tauri::command]
fn sync_next_local_sequence(state: State<'_, AppState>) -> Result<i64, CommandError> {
    with_db!(state, db, db.next_local_sequence())
}

#[tauri::command]
fn sync_list_pending(state: State<'_, AppState>) -> Result<Vec<SyncOutboxItem>, CommandError> {
    with_db!(state, db, db.list_pending_sync())
}

#[tauri::command]
fn sync_list_by_status(
    state: State<'_, AppState>,
    status: String,
) -> Result<Vec<SyncOutboxItem>, CommandError> {
    with_db!(state, db, db.list_sync_by_status(&status))
}

#[tauri::command]
fn sync_update_mutation_state(
    state: State<'_, AppState>,
    client_mutation_id: String,
    status: String,
    last_error: Option<String>,
    updated_at: String,
) -> Result<(), CommandError> {
    with_db!(
        state,
        db,
        db.update_mutation_state(
            &client_mutation_id,
            &status,
            last_error.as_deref(),
            &updated_at,
        )
    )
}

#[tauri::command]
fn sync_persist_ack(
    state: State<'_, AppState>,
    client_mutation_id: String,
    receipt_json: String,
    ack_persisted_at: String,
) -> Result<(), CommandError> {
    with_db!(
        state,
        db,
        db.persist_sync_ack(&client_mutation_id, &receipt_json, &ack_persisted_at)
    )
}

#[tauri::command]
fn sync_get_counts(state: State<'_, AppState>) -> Result<SyncCounts, CommandError> {
    with_db!(state, db, db.get_sync_counts())
}

#[tauri::command]
fn sync_offline_state(
    state: State<'_, AppState>,
    section_id: Option<String>,
) -> Result<OfflineState, CommandError> {
    with_db!(
        state,
        db,
        db.offline_state(section_id.as_deref(), Utc::now())
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let (db_key, key_source) = resolve_db_key().unwrap_or_else(|err| {
        eprintln!("WAIKE Learning OS key error: {err}");
        eprintln!("Set WAIKE_DEV_DB_KEY to a 64-hex-char key for local development.");
        std::process::exit(1);
    });
    let verify_key = load_verify_key().unwrap_or_else(|err| {
        eprintln!("WAIKE Learning OS verify key error: {err}");
        std::process::exit(1);
    });
    let data_dir = default_data_dir();
    let service = PackService::new(data_dir, &verify_key, db_key).unwrap_or_else(|err| {
        eprintln!("WAIKE Learning OS storage error: {err}");
        std::process::exit(1);
    });

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState {
            service: Mutex::new(service),
            key_source,
        })
        .invoke_handler(tauri::generate_handler![
            get_key_source,
            list_installed_packs,
            install_learner_pack,
            get_trust_status,
            list_lessons,
            open_lesson,
            save_lesson_position,
            get_resume_position,
            sync_cache_lease,
            sync_get_lease,
            sync_list_leases,
            sync_mark_lease_revoked,
            sync_mark_lease_expired,
            sync_enqueue_mutation,
            sync_next_local_sequence,
            sync_list_pending,
            sync_list_by_status,
            sync_update_mutation_state,
            sync_persist_ack,
            sync_get_counts,
            sync_offline_state,
        ])
        .run(tauri::generate_context!())
        .expect("error while running WAIKE Learning OS");
}
