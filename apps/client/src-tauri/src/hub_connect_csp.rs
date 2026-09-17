//! Policy-aligned webview `connect-src` for Runtime Hub.
//!
//! Static `tauri.conf.json` CSP stays fail-closed (`'self'` + Tauri IPC only).
//! Before the webview starts, we load HubEndpointPolicy v1 (and optional compile-time
//! `VITE_HUB_URL`) and append **exact** authorized Hub origin(s) — never scheme-wide
//! `http:` / `https:` / `ws:` / `wss:`.
//!
//! Native HubEndpointPolicy remains the credential trust boundary; CSP is defense-in-depth
//! so untrusted hosts cannot receive `fetch`/WebSocket traffic from the webview.

use crate::hub_endpoint_policy::{
    load_hub_endpoint_policy, parse_hub_base_url, HubEndpointPolicy,
};
use std::collections::HashMap;
use tauri::utils::config::{Csp, CspDirectiveSources};
use url::Url;

/// Baseline connect-src sources when no Hub is authorized.
/// Explicit `connect-src` overrides `default-src`, so Tauri IPC must be listed.
pub const BASE_CONNECT_SRC: &[&str] = &[
    "'self'",
    "ipc:",
    "http://ipc.localhost",
    "https://ipc.localhost",
];

/// Derive CSP connect-src origins (HTTP(S) + matching WS(S)) from a normalized Hub base.
pub fn connect_origins_for_hub_base(authorized_base: &str) -> Result<Vec<String>, String> {
    let normalized = parse_hub_base_url(authorized_base)?;
    let parsed = Url::parse(&normalized).map_err(|_| "hub_csp_origin_parse_failed".to_string())?;
    let origin = parsed.origin().ascii_serialization();
    if origin == "null" {
        return Err("hub_csp_origin_opaque".into());
    }
    let ws_origin = match parsed.scheme() {
        "https" => origin.replacen("https://", "wss://", 1),
        "http" => origin.replacen("http://", "ws://", 1),
        other => return Err(format!("hub_csp_scheme_unsupported:{other}")),
    };
    Ok(vec![origin, ws_origin])
}

/// Build the full CSP policy string: preserve non-connect directives, set connect-src
/// to `'self'` + IPC + authorized Hub origins only.
pub fn build_csp_with_hub_connect(
    base_csp: &str,
    authorized_hub_bases: &[String],
) -> Result<String, String> {
    let mut map: HashMap<String, CspDirectiveSources> =
        Csp::Policy(base_csp.to_string()).into();

    let mut connect: Vec<String> = BASE_CONNECT_SRC
        .iter()
        .map(|s| (*s).to_string())
        .collect();

    for base in authorized_hub_bases {
        for origin in connect_origins_for_hub_base(base)? {
            if !connect.contains(&origin) {
                connect.push(origin);
            }
        }
    }

    // Refuse scheme-wide wildcards — that would undo HubEndpointPolicy.
    for src in &connect {
        if matches!(src.as_str(), "http:" | "https:" | "ws:" | "wss:") {
            return Err(format!("hub_csp_scheme_wildcard_forbidden:{src}"));
        }
    }

    map.insert("connect-src".into(), CspDirectiveSources::List(connect));
    Ok(Csp::DirectiveMap(map).to_string())
}

/// Collect Hub bases that may receive webview connect traffic.
///
/// Sources (additive, each must already be a trusted config surface):
/// 1. HubEndpointPolicy `authorized_hub_base_url` when policy loads + validates
/// 2. Compile-time `VITE_HUB_URL` (school image bake) when present
pub fn authorized_hub_bases_for_csp(
    policy: Option<&HubEndpointPolicy>,
    compile_time_hub: Option<&str>,
) -> Result<Vec<String>, String> {
    let mut bases = Vec::new();
    if let Some(p) = policy {
        p.validate_shape()?;
        bases.push(parse_hub_base_url(&p.authorized_hub_base_url)?);
    }
    if let Some(raw) = compile_time_hub.map(str::trim).filter(|s| !s.is_empty()) {
        let n = parse_hub_base_url(raw)?;
        if !bases.contains(&n) {
            bases.push(n);
        }
    }
    Ok(bases)
}

/// Load provisioned policy + compile-time Hub and compute the runtime CSP string.
pub fn resolve_runtime_hub_csp(base_csp: &str) -> Result<String, String> {
    let policy = load_hub_endpoint_policy()?;
    let compile_time = option_env!("VITE_HUB_URL");
    let bases = authorized_hub_bases_for_csp(policy.as_ref(), compile_time)?;
    build_csp_with_hub_connect(base_csp, &bases)
}

/// Apply policy-scoped connect-src onto a Tauri context config (before `.run`).
pub fn apply_hub_connect_csp_to_config(csp_slot: &mut Option<Csp>) -> Result<(), String> {
    let base = match csp_slot.as_ref() {
        Some(Csp::Policy(s)) => s.clone(),
        Some(other) => other.to_string(),
        None => {
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost"
                .to_string()
        }
    };
    let updated = resolve_runtime_hub_csp(&base)?;
    *csp_slot = Some(Csp::Policy(updated));
    Ok(())
}

/// Whether a CSP policy string permits connect to `target_url` (scheme+host+port).
#[cfg(test)]
pub fn csp_connect_allows(csp: &str, target_url: &str) -> Result<bool, String> {
    let map: HashMap<String, CspDirectiveSources> = Csp::Policy(csp.to_string()).into();
    let sources: Vec<String> = map
        .get("connect-src")
        .cloned()
        .unwrap_or_default()
        .into();
    let origins = connect_origins_for_hub_base(target_url)?;
    let http_origin = origins
        .first()
        .ok_or_else(|| "hub_csp_missing_origin".to_string())?;
    Ok(sources.iter().any(|s| s == http_origin || s == "http:" || s == "https:"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hub_endpoint_policy::{parse_policy_json, with_policy_env};

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
      "authorized_hub_base_url": "http://10.0.2.100:8787",
      "deployment_id": "device-lab-qemu-guest",
      "site_id": "device-lab",
      "require_https": false,
      "allow_insecure_local": true,
      "provenance": "device_lab_fixture",
      "expires_at": null
    }"#;

    const BASE: &str = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost";

    #[test]
    fn authorized_https_hub_origin_allowed_in_connect_src() {
        let policy = parse_policy_json(SCHOOL_HTTPS).unwrap();
        let bases = authorized_hub_bases_for_csp(Some(&policy), None).unwrap();
        let csp = build_csp_with_hub_connect(BASE, &bases).unwrap();
        assert!(
            csp_connect_allows(&csp, "https://hub.school.example/api/v1/auth/login").unwrap()
        );
        assert!(csp.contains("https://hub.school.example"));
        assert!(csp.contains("wss://hub.school.example"));
        // Scheme-wide tokens must not appear as bare sources.
        let map: HashMap<String, CspDirectiveSources> = Csp::Policy(csp.clone()).into();
        let sources: Vec<String> = map.get("connect-src").cloned().unwrap().into();
        assert!(!sources.iter().any(|s| s == "https:" || s == "http:" || s == "ws:" || s == "wss:"));
    }

    #[test]
    fn unauthorized_origin_not_in_connect_src() {
        let policy = parse_policy_json(SCHOOL_HTTPS).unwrap();
        let bases = authorized_hub_bases_for_csp(Some(&policy), None).unwrap();
        let csp = build_csp_with_hub_connect(BASE, &bases).unwrap();
        assert!(!csp_connect_allows(&csp, "https://evil.example").unwrap());
        assert!(!csp.contains("evil.example"));
    }

    #[test]
    fn device_lab_insecure_local_only_exact_authorized_origin() {
        let policy = parse_policy_json(DEVICE_LAB_HTTP).unwrap();
        let bases = authorized_hub_bases_for_csp(Some(&policy), None).unwrap();
        let csp = build_csp_with_hub_connect(BASE, &bases).unwrap();
        assert!(csp_connect_allows(&csp, "http://10.0.2.100:8787/").unwrap());
        assert!(csp.contains("http://10.0.2.100:8787"));
        assert!(csp.contains("ws://10.0.2.100:8787"));
        // Neighbor / alternate lab addresses stay blocked at CSP layer.
        assert!(!csp_connect_allows(&csp, "http://10.0.2.2:8787").unwrap());
        assert!(!csp_connect_allows(&csp, "http://127.0.0.1:8787").unwrap());
        assert!(!csp_connect_allows(&csp, "http://evil.example").unwrap());
    }

    #[test]
    fn missing_policy_fail_closed_connect_src() {
        with_policy_env(None, None, || {
            let csp = resolve_runtime_hub_csp(BASE).unwrap();
            let map: HashMap<String, CspDirectiveSources> = Csp::Policy(csp.clone()).into();
            let sources: Vec<String> = map.get("connect-src").cloned().unwrap().into();
            assert!(sources.contains(&"'self'".into()));
            assert!(sources.iter().any(|s| s.starts_with("ipc")));
            assert!(!sources.iter().any(|s| s.starts_with("http://") && !s.contains("ipc.localhost")));
            assert!(!sources.iter().any(|s| s.starts_with("https://") && !s.contains("ipc.localhost")));
            assert!(!csp_connect_allows(&csp, "https://hub.school.example").unwrap());
        });
    }

    #[test]
    fn policy_env_injects_device_lab_origin() {
        with_policy_env(Some(DEVICE_LAB_HTTP), None, || {
            let csp = resolve_runtime_hub_csp(BASE).unwrap();
            assert!(csp_connect_allows(&csp, "http://10.0.2.100:8787").unwrap());
            assert!(!csp_connect_allows(&csp, "https://evil.example").unwrap());
        });
    }

    #[test]
    fn credential_path_still_fail_closed_without_policy_authorization() {
        // Defense-in-depth: CSP omit is not enough alone; HubEndpointPolicy must reject.
        with_policy_env(Some(SCHOOL_HTTPS), None, || {
            use crate::hub_endpoint_policy::authorize_launch_hub_url;
            assert_eq!(
                authorize_launch_hub_url("https://evil.example").unwrap_err(),
                "hub_url_not_in_policy"
            );
            let csp = resolve_runtime_hub_csp(BASE).unwrap();
            assert!(!csp_connect_allows(&csp, "https://evil.example").unwrap());
        });
    }

    #[test]
    fn rejects_building_csp_that_embeds_scheme_wildcards_as_hub_base() {
        // connect_origins_for_hub_base requires a real URL; scheme tokens fail parse.
        assert!(connect_origins_for_hub_base("https:").is_err());
        assert!(connect_origins_for_hub_base("http:").is_err());
    }

    #[test]
    fn compile_time_hub_additive_with_policy() {
        let policy = parse_policy_json(DEVICE_LAB_HTTP).unwrap();
        let bases = authorized_hub_bases_for_csp(
            Some(&policy),
            Some("https://hub.school.example/"),
        )
        .unwrap();
        let csp = build_csp_with_hub_connect(BASE, &bases).unwrap();
        assert!(csp_connect_allows(&csp, "http://10.0.2.100:8787").unwrap());
        assert!(csp_connect_allows(&csp, "https://hub.school.example").unwrap());
    }
}
