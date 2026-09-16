//! HubEndpointPolicy v1 — trusted authorization for runtime Hub base URLs.
//!
//! Launch-context `hub_url` may *request* a Hub. This module is the native trust
//! boundary that parses URLs and authorizes them against a provisioned policy.
//! Launch context alone is never sufficient to send credentials/tokens.

use chrono::{DateTime, Utc};
use serde::Deserialize;
use std::env;
use std::fs;
use std::path::PathBuf;
use url::Url;

const SCHEMA_VERSION: &str = "hub_endpoint_policy.v1";

#[cfg(test)]
use std::sync::Mutex;

/// Serialize policy-test env mutations (parallel cargo tests).
#[cfg(test)]
static POLICY_ENV_LOCK: Mutex<()> = Mutex::new(());

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct HubEndpointPolicy {
    pub schema_version: String,
    pub authorized_hub_base_url: String,
    pub deployment_id: String,
    #[serde(default)]
    pub site_id: Option<String>,
    pub require_https: bool,
    pub allow_insecure_local: bool,
    pub provenance: String,
    #[serde(default)]
    pub expires_at: Option<String>,
}

impl HubEndpointPolicy {
    pub fn validate_shape(&self) -> Result<(), String> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(format!(
                "hub_policy_schema_version:{}",
                self.schema_version
            ));
        }
        if self.deployment_id.trim().is_empty() {
            return Err("hub_policy_deployment_id_empty".into());
        }
        match self.provenance.as_str() {
            "managed_policy" | "owner_bundle" | "enrollment" | "device_lab_fixture" | "test" => {}
            other => return Err(format!("hub_policy_provenance:{other}")),
        }
        // Authorized URL must itself be structurally valid.
        let _ = parse_hub_base_url(&self.authorized_hub_base_url)?;
        if self.authorized_hub_base_url.to_ascii_lowercase().starts_with("http://")
            && !self.allow_insecure_local
        {
            return Err("hub_policy_http_requires_allow_insecure_local".into());
        }
        Ok(())
    }

    pub fn is_expired(&self, now: DateTime<Utc>) -> Result<bool, String> {
        let Some(raw) = self.expires_at.as_ref().map(|s| s.trim()).filter(|s| !s.is_empty()) else {
            return Ok(false);
        };
        let exp = DateTime::parse_from_rfc3339(raw)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|_| "hub_policy_expires_at_invalid".to_string())?;
        Ok(now >= exp)
    }
}

/// Structurally parse and canonicalize a Hub base URL at the native trust boundary.
///
/// Rejects userinfo, fragments, queries, control/NUL, backslash confusion, empty host,
/// unsupported schemes, and malformed ports (via the URL parser).
pub fn parse_hub_base_url(raw: &str) -> Result<String, String> {
    if raw.is_empty() {
        return Err("hub_url_empty".into());
    }
    if raw.contains('\0') || raw.chars().any(|c| c.is_control()) {
        return Err("hub_url_control_char".into());
    }
    if raw.contains('\\') {
        return Err("hub_url_backslash".into());
    }
    if raw.chars().any(|c| c.is_whitespace()) {
        return Err("hub_url_whitespace".into());
    }

    let parsed = Url::parse(raw).map_err(|_| "hub_url_parse_failed".to_string())?;

    match parsed.scheme() {
        "https" | "http" => {}
        "file" => return Err("hub_url_scheme_file".into()),
        "javascript" => return Err("hub_url_scheme_javascript".into()),
        other => return Err(format!("hub_url_scheme_unsupported:{other}")),
    }

    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("hub_url_userinfo".into());
    }
    if parsed.fragment().is_some() {
        return Err("hub_url_fragment".into());
    }
    if parsed.query().is_some() {
        return Err("hub_url_query".into());
    }

    let host = parsed
        .host_str()
        .map(str::to_ascii_lowercase)
        .filter(|h| !h.is_empty())
        .ok_or_else(|| "hub_url_empty_host".to_string())?;

    if let Some(port) = parsed.port() {
        if port == 0 {
            return Err("hub_url_port_invalid".into());
        }
    }

    let mut out = format!("{}://{}", parsed.scheme(), host);
    if let Some(port) = parsed.port() {
        out.push(':');
        out.push_str(&port.to_string());
    }

    let path = parsed.path();
    if path != "/" && !path.is_empty() {
        let mut path_norm = path.trim_end_matches('/').to_string();
        if path_norm.is_empty() {
            path_norm = "/".into();
        }
        if path_norm != "/" {
            out.push_str(&path_norm);
        }
    }

    Ok(out)
}

/// Authorize a requested Hub URL against trusted policy. Returns normalized base.
pub fn authorize_hub_url(raw: &str, policy: &HubEndpointPolicy) -> Result<String, String> {
    policy.validate_shape()?;
    if policy.is_expired(Utc::now())? {
        return Err("hub_policy_expired".into());
    }

    let candidate = parse_hub_base_url(raw)?;
    let authorized = parse_hub_base_url(&policy.authorized_hub_base_url)?;

    let is_http = candidate.starts_with("http://");
    let is_https = candidate.starts_with("https://");
    if !is_http && !is_https {
        return Err("hub_url_scheme_unsupported".into());
    }

    // Plain HTTP only via explicit local/test exception on the trusted policy.
    if is_http && !policy.allow_insecure_local {
        return Err("hub_url_http_not_allowed".into());
    }
    if policy.require_https && is_http && !policy.allow_insecure_local {
        return Err("hub_url_https_required".into());
    }

    if candidate != authorized {
        return Err("hub_url_not_in_policy".into());
    }
    Ok(candidate)
}

pub fn parse_policy_json(text: &str) -> Result<HubEndpointPolicy, String> {
    let policy: HubEndpointPolicy =
        serde_json::from_str(text).map_err(|_| "hub_policy_json_invalid".to_string())?;
    policy.validate_shape()?;
    // Normalize authorized URL in-place via re-parse equality check.
    let _ = parse_hub_base_url(&policy.authorized_hub_base_url)?;
    Ok(policy)
}

/// Load HubEndpointPolicy from trusted provisioned sources (never from launch JSON alone).
///
/// Precedence:
/// 1. `WAIKE_HUB_ENDPOINT_POLICY_JSON` (inline; Device Lab / CI)
/// 2. `WAIKE_HUB_ENDPOINT_POLICY_PATH` (explicit file)
/// 3. `{data_dir}/com.gunnchos.waike.learning/hub_endpoint_policy.v1.json` (managed deploy)
pub fn load_hub_endpoint_policy() -> Result<Option<HubEndpointPolicy>, String> {
    if let Ok(json) = env::var("WAIKE_HUB_ENDPOINT_POLICY_JSON") {
        let trimmed = json.trim();
        if !trimmed.is_empty() {
            return Ok(Some(parse_policy_json(trimmed)?));
        }
    }
    if let Ok(path) = env::var("WAIKE_HUB_ENDPOINT_POLICY_PATH") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return Ok(Some(load_policy_file(PathBuf::from(trimmed))?));
        }
    }
    if let Some(dir) = dirs::data_dir() {
        let p = dir
            .join("com.gunnchos.waike.learning")
            .join("hub_endpoint_policy.v1.json");
        if p.is_file() {
            return Ok(Some(load_policy_file(p)?));
        }
    }
    Ok(None)
}

fn load_policy_file(path: PathBuf) -> Result<HubEndpointPolicy, String> {
    let text = fs::read_to_string(&path).map_err(|e| format!("hub_policy_read:{e}"))?;
    parse_policy_json(&text)
}

/// Authorize launch-context `hub_url` using the currently provisioned policy.
pub fn authorize_launch_hub_url(raw: &str) -> Result<String, String> {
    let policy = load_hub_endpoint_policy()?
        .ok_or_else(|| "hub_url_policy_missing".to_string())?;
    authorize_hub_url(raw, &policy)
}

/// Test helper: run `f` with exclusive policy env + restore afterward.
#[cfg(test)]
pub fn with_policy_env<F, R>(json: Option<&str>, path: Option<&str>, f: F) -> R
where
    F: FnOnce() -> R,
{
    let _guard = POLICY_ENV_LOCK.lock().unwrap();
    let prev_json = env::var("WAIKE_HUB_ENDPOINT_POLICY_JSON").ok();
    let prev_path = env::var("WAIKE_HUB_ENDPOINT_POLICY_PATH").ok();
    match json {
        Some(v) => env::set_var("WAIKE_HUB_ENDPOINT_POLICY_JSON", v),
        None => env::remove_var("WAIKE_HUB_ENDPOINT_POLICY_JSON"),
    }
    match path {
        Some(v) => env::set_var("WAIKE_HUB_ENDPOINT_POLICY_PATH", v),
        None => env::remove_var("WAIKE_HUB_ENDPOINT_POLICY_PATH"),
    }
    let out = f();
    match prev_json {
        Some(v) => env::set_var("WAIKE_HUB_ENDPOINT_POLICY_JSON", v),
        None => env::remove_var("WAIKE_HUB_ENDPOINT_POLICY_JSON"),
    }
    match prev_path {
        Some(v) => env::set_var("WAIKE_HUB_ENDPOINT_POLICY_PATH", v),
        None => env::remove_var("WAIKE_HUB_ENDPOINT_POLICY_PATH"),
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCHOOL_HTTPS: &str = r#"{
      "schema_version": "hub_endpoint_policy.v1",
      "authorized_hub_base_url": "https://hub.school.example",
      "deployment_id": "school-alpha",
      "site_id": "site-alpha",
      "require_https": true,
      "allow_insecure_local": false,
      "provenance": "managed_policy",
      "expires_at": null
    }"#;

    const DEVICE_LAB_HTTP: &str = r#"{
      "schema_version": "hub_endpoint_policy.v1",
      "authorized_hub_base_url": "http://10.0.2.2:8787",
      "deployment_id": "device-lab-qemu-guest",
      "site_id": "device-lab",
      "require_https": false,
      "allow_insecure_local": true,
      "provenance": "device_lab_fixture",
      "expires_at": null
    }"#;

    #[test]
    fn accepts_authorized_https_school() {
        let policy = parse_policy_json(SCHOOL_HTTPS).unwrap();
        let n = authorize_hub_url("https://hub.school.example/", &policy).unwrap();
        assert_eq!(n, "https://hub.school.example");
    }

    #[test]
    fn accepts_device_lab_http_with_explicit_policy() {
        let policy = parse_policy_json(DEVICE_LAB_HTTP).unwrap();
        let n = authorize_hub_url("http://10.0.2.2:8787/", &policy).unwrap();
        assert_eq!(n, "http://10.0.2.2:8787");
    }

    #[test]
    fn trailing_slash_normalization() {
        assert_eq!(
            parse_hub_base_url("https://hub.school.example/").unwrap(),
            "https://hub.school.example"
        );
        assert_eq!(
            parse_hub_base_url("https://hub.school.example/api/").unwrap(),
            "https://hub.school.example/api"
        );
    }

    #[test]
    fn rejects_path_file_javascript_userinfo_fragment_control_backslash() {
        assert!(parse_hub_base_url("/etc/passwd").is_err());
        assert_eq!(
            parse_hub_base_url("file:///etc/passwd").unwrap_err(),
            "hub_url_scheme_file"
        );
        assert_eq!(
            parse_hub_base_url("javascript:alert(1)").unwrap_err(),
            "hub_url_scheme_javascript"
        );
        assert_eq!(
            parse_hub_base_url("https://user:password@hub.example").unwrap_err(),
            "hub_url_userinfo"
        );
        assert_eq!(
            parse_hub_base_url("https://hub.example/path#frag").unwrap_err(),
            "hub_url_fragment"
        );
        assert_eq!(
            parse_hub_base_url("https://hub.example/path?x=1").unwrap_err(),
            "hub_url_query"
        );
        assert!(parse_hub_base_url("https://hub.example/\0x").is_err());
        assert_eq!(
            parse_hub_base_url("https://hub.example/foo\\bar").unwrap_err(),
            "hub_url_backslash"
        );
        // Structurally valid evil hosts are rejected by policy equality, not parse.
        assert!(parse_hub_base_url("http://evil.example").is_ok());
        assert!(parse_hub_base_url("https://evil.example").is_ok());
    }

    #[test]
    fn rejects_malformed_port() {
        assert!(parse_hub_base_url("https://hub.example:99999").is_err());
        assert!(parse_hub_base_url("https://hub.example:notaport").is_err());
    }

    #[test]
    fn policy_rejects_unauthorized_endpoints() {
        let policy = parse_policy_json(SCHOOL_HTTPS).unwrap();
        assert_eq!(
            authorize_hub_url("https://evil.example", &policy).unwrap_err(),
            "hub_url_not_in_policy"
        );
        assert_eq!(
            authorize_hub_url("http://evil.example", &policy).unwrap_err(),
            "hub_url_http_not_allowed"
        );
        let lab = parse_policy_json(DEVICE_LAB_HTTP).unwrap();
        assert_eq!(
            authorize_hub_url("http://127.0.0.1:8787", &lab).unwrap_err(),
            "hub_url_not_in_policy"
        );
    }

    #[test]
    fn endpoint_absent_from_policy_fails_closed() {
        with_policy_env(None, None, || {
            assert_eq!(
                authorize_launch_hub_url("https://hub.school.example").unwrap_err(),
                "hub_url_policy_missing"
            );
        });
    }

    #[test]
    fn load_policy_from_json_env() {
        with_policy_env(Some(DEVICE_LAB_HTTP), None, || {
            let n = authorize_launch_hub_url("http://10.0.2.2:8787").unwrap();
            assert_eq!(n, "http://10.0.2.2:8787");
        });
    }
}
