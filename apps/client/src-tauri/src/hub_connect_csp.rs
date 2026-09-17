//! Policy-aligned webview `connect-src` for Runtime Hub.
//!
//! Static `tauri.conf.json` CSP stays fail-closed (`'self'` + Tauri IPC only).
//! Before the webview starts, we load HubEndpointPolicy v1 (and optional compile-time
//! `VITE_HUB_URL`) and append **exact** authorized Hub origin(s) — never scheme-wide
//! `http:` / `https:` / `ws:` / `wss:`.
//!
//! Native HubEndpointPolicy remains the credential trust boundary; CSP is defense-in-depth
//! so untrusted hosts cannot receive `fetch`/WebSocket traffic from the webview.
//!
//! ## Runtime apply contract (WebKitGTK / Device Lab)
//! Tauri serves CSP primarily via the custom-protocol response header. WebKitGTK has
//! historically been unreliable about honoring those headers for `tauri://` documents.
//! After mutating `Context::config_mut().app.security.csp`, we also inject the same
//! effective policy as an HTML `<meta http-equiv="Content-Security-Policy">` so the
//! running WebView's effective `connect-src` matches the policy-authorized Hub origin
//! before first navigation/fetch.

use crate::hub_endpoint_policy::{
    load_hub_endpoint_policy, parse_hub_base_url, HubEndpointPolicy,
};
use std::borrow::Cow;
use std::collections::HashMap;
use tauri::utils::assets::{AssetKey, AssetsIter, CspHash};
use tauri::utils::config::{Csp, CspDirectiveSources};
use tauri::{Assets, Runtime};
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
    let map = build_csp_directive_map(base_csp, authorized_hub_bases)?;
    Ok(Csp::DirectiveMap(map).to_string())
}

fn build_csp_directive_map(
    base_csp: &str,
    authorized_hub_bases: &[String],
) -> Result<HashMap<String, CspDirectiveSources>, String> {
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
    Ok(map)
}

/// Collect Hub bases that may receive webview connect traffic.
///
/// Sources (additive, each must already be a trusted config surface):
/// 1. HubEndpointPolicy `authorized_hub_base_url` when policy loads + validates
/// 2. Compile-time `VITE_HUB_URL` (school image bake) when present
/// 3. Launch-context hub already authorized by `authorize_launch_hub_url` (same process)
pub fn authorized_hub_bases_for_csp(
    policy: Option<&HubEndpointPolicy>,
    compile_time_hub: Option<&str>,
) -> Result<Vec<String>, String> {
    authorized_hub_bases_for_csp_with_launch(policy, compile_time_hub, None)
}

/// Same as [`authorized_hub_bases_for_csp`], plus an optional already-authorized launch hub.
pub fn authorized_hub_bases_for_csp_with_launch(
    policy: Option<&HubEndpointPolicy>,
    compile_time_hub: Option<&str>,
    launch_authorized_hub: Option<&str>,
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
    if let Some(raw) = launch_authorized_hub.map(str::trim).filter(|s| !s.is_empty()) {
        let n = parse_hub_base_url(raw)?;
        if !bases.contains(&n) {
            bases.push(n);
        }
    }
    Ok(bases)
}

/// Load provisioned policy + compile-time Hub and compute the runtime CSP string.
pub fn resolve_runtime_hub_csp(base_csp: &str) -> Result<String, String> {
    resolve_runtime_hub_csp_with_launch(base_csp, None)
}

/// Resolve runtime CSP, optionally folding in a launch-context hub already authorized
/// by HubEndpointPolicy in this process.
pub fn resolve_runtime_hub_csp_with_launch(
    base_csp: &str,
    launch_authorized_hub: Option<&str>,
) -> Result<String, String> {
    let policy = load_hub_endpoint_policy()?;
    let compile_time = option_env!("VITE_HUB_URL");
    let bases =
        authorized_hub_bases_for_csp_with_launch(policy.as_ref(), compile_time, launch_authorized_hub)?;
    build_csp_with_hub_connect(base_csp, &bases)
}

/// Result of applying policy-scoped connect-src onto the Tauri config CSP slot.
#[derive(Debug, Clone)]
pub struct AppliedHubConnectCsp {
    /// Full effective CSP policy string (also stored on the config slot).
    pub effective_csp: String,
    /// `connect-src` source list after apply.
    pub connect_src: Vec<String>,
}

/// Extract connect-src sources from a CSP policy string.
pub fn connect_src_sources(csp: &str) -> Vec<String> {
    let map: HashMap<String, CspDirectiveSources> = Csp::Policy(csp.to_string()).into();
    map.get("connect-src")
        .cloned()
        .map(Into::into)
        .unwrap_or_default()
}

/// Whether a CSP policy string permits connect to `target_url` (scheme+host+port).
pub fn csp_connect_allows(csp: &str, target_url: &str) -> Result<bool, String> {
    let sources = connect_src_sources(csp);
    let origins = connect_origins_for_hub_base(target_url)?;
    let http_origin = origins
        .first()
        .ok_or_else(|| "hub_csp_missing_origin".to_string())?;
    Ok(sources
        .iter()
        .any(|s| s == http_origin || s == "http:" || s == "https:"))
}

/// Apply policy-scoped connect-src onto a Tauri context config (before `.run`).
///
/// Stores a [`Csp::DirectiveMap`] (not a re-parsed Policy string) and returns the
/// effective policy for logging + HTML meta injection.
pub fn apply_hub_connect_csp_to_config(
    csp_slot: &mut Option<Csp>,
) -> Result<AppliedHubConnectCsp, String> {
    apply_hub_connect_csp_to_config_with_launch(csp_slot, None)
}

/// Apply CSP, folding in an already-authorized launch hub base when present.
pub fn apply_hub_connect_csp_to_config_with_launch(
    csp_slot: &mut Option<Csp>,
    launch_authorized_hub: Option<&str>,
) -> Result<AppliedHubConnectCsp, String> {
    let base = match csp_slot.as_ref() {
        Some(Csp::Policy(s)) => s.clone(),
        Some(other) => other.to_string(),
        None => {
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost"
                .to_string()
        }
    };
    let policy = load_hub_endpoint_policy()?;
    let compile_time = option_env!("VITE_HUB_URL");
    let bases =
        authorized_hub_bases_for_csp_with_launch(policy.as_ref(), compile_time, launch_authorized_hub)?;
    let map = build_csp_directive_map(&base, &bases)?;
    let connect_src: Vec<String> = map
        .get("connect-src")
        .cloned()
        .map(Into::into)
        .unwrap_or_default();
    let effective_csp = Csp::DirectiveMap(map.clone()).to_string();

    // If launch authorized a Hub, the effective connect-src MUST include that origin.
    if let Some(hub) = launch_authorized_hub.map(str::trim).filter(|s| !s.is_empty()) {
        if !csp_connect_allows(&effective_csp, hub)? {
            return Err(format!(
                "hub_csp_launch_origin_missing_after_apply:{hub}"
            ));
        }
    }

    *csp_slot = Some(Csp::DirectiveMap(map));
    Ok(AppliedHubConnectCsp {
        effective_csp,
        connect_src,
    })
}

/// Inject (or replace) a CSP meta tag so WebKitGTK applies the policy even when
/// custom-protocol response headers are ignored.
pub fn inject_csp_meta_html(html: &str, csp: &str) -> String {
    let escaped = csp
        .replace('&', "&amp;")
        .replace('"', "&quot;");
    let meta = format!(
        r#"<meta http-equiv="Content-Security-Policy" content="{escaped}">"#
    );
    // Replace an existing CSP meta if present (keep a single effective policy).
    let re_existing = regex_lite_replace_csp_meta(html, &meta);
    if re_existing.0 {
        return re_existing.1;
    }
    if let Some(idx) = html.find("</head>") {
        let mut out = String::with_capacity(html.len() + meta.len() + 1);
        out.push_str(&html[..idx]);
        out.push_str(&meta);
        out.push('\n');
        out.push_str(&html[idx..]);
        return out;
    }
    if let Some(idx) = html.find("<head>") {
        let insert_at = idx + "<head>".len();
        let mut out = String::with_capacity(html.len() + meta.len() + 1);
        out.push_str(&html[..insert_at]);
        out.push('\n');
        out.push_str(&meta);
        out.push_str(&html[insert_at..]);
        return out;
    }
    format!("{meta}\n{html}")
}

fn regex_lite_replace_csp_meta(html: &str, new_meta: &str) -> (bool, String) {
    // Avoid a regex crate dependency: scan for Content-Security-Policy meta tags.
    let lower = html.to_ascii_lowercase();
    let Some(start) = lower.find("http-equiv=\"content-security-policy\"")
        .or_else(|| lower.find("http-equiv='content-security-policy'"))
    else {
        return (false, html.to_string());
    };
    let tag_start = html[..start].rfind('<').unwrap_or(0);
    let Some(rel_end) = html[start..].find('>') else {
        return (false, html.to_string());
    };
    let tag_end = start + rel_end + 1;
    let mut out = String::with_capacity(html.len() + new_meta.len());
    out.push_str(&html[..tag_start]);
    out.push_str(new_meta);
    out.push_str(&html[tag_end..]);
    (true, out)
}

/// Assets wrapper that injects the effective CSP meta into HTML documents.
pub struct HtmlCspMetaAssets<R: Runtime> {
    inner: Box<dyn Assets<R>>,
    csp: String,
}

impl<R: Runtime> HtmlCspMetaAssets<R> {
    pub fn wrap(inner: Box<dyn Assets<R>>, csp: String) -> Self {
        Self { inner, csp }
    }
}

impl<R: Runtime> Assets<R> for HtmlCspMetaAssets<R> {
    fn get(&self, key: &AssetKey) -> Option<Cow<'_, [u8]>> {
        let bytes = self.inner.get(key)?;
        let path = key.as_ref();
        let is_html = path.ends_with(".html")
            || path.ends_with(".htm")
            || path.ends_with("/index.html")
            || path == "/index.html"
            || path == "index.html";
        if !is_html {
            return Some(bytes);
        }
        let html = String::from_utf8_lossy(&bytes);
        let injected = inject_csp_meta_html(&html, &self.csp);
        Some(Cow::Owned(injected.into_bytes()))
    }

    fn iter(&self) -> Box<AssetsIter<'_>> {
        self.inner.iter()
    }

    fn csp_hashes(&self, html_path: &AssetKey) -> Box<dyn Iterator<Item = CspHash<'_>> + '_> {
        self.inner.csp_hashes(html_path)
    }
}

/// Install HTML CSP meta injection on the Tauri context assets (before `.run`).
pub fn install_html_csp_meta_assets<R: Runtime>(
    context: &mut tauri::Context<R>,
    effective_csp: &str,
) {
    struct EmptyAssets;
    impl<R: Runtime> Assets<R> for EmptyAssets {
        fn get(&self, _key: &AssetKey) -> Option<Cow<'_, [u8]>> {
            None
        }
        fn iter(&self) -> Box<AssetsIter<'_>> {
            Box::new(std::iter::empty())
        }
        fn csp_hashes(&self, _html_path: &AssetKey) -> Box<dyn Iterator<Item = CspHash<'_>> + '_> {
            Box::new(std::iter::empty())
        }
    }

    let previous = context.set_assets(Box::new(EmptyAssets));
    let wrapped = HtmlCspMetaAssets::wrap(previous, effective_csp.to_string());
    let _ = context.set_assets(Box::new(wrapped));
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
        let sources = connect_src_sources(&csp);
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
            let sources = connect_src_sources(&csp);
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

    #[test]
    fn apply_mutates_config_slot_with_authorized_origin_not_evil() {
        with_policy_env(Some(DEVICE_LAB_HTTP), None, || {
            let mut slot: Option<Csp> = Some(Csp::Policy(BASE.to_string()));
            let applied = apply_hub_connect_csp_to_config_with_launch(
                &mut slot,
                Some("http://10.0.2.100:8787"),
            )
            .unwrap();
            assert!(matches!(slot, Some(Csp::DirectiveMap(_))));
            assert!(
                csp_connect_allows(&applied.effective_csp, "http://10.0.2.100:8787").unwrap()
            );
            assert!(!csp_connect_allows(&applied.effective_csp, "https://evil.example").unwrap());
            assert!(applied
                .connect_src
                .iter()
                .any(|s| s == "http://10.0.2.100:8787"));
            assert!(!applied.connect_src.iter().any(|s| s.contains("evil")));
            // Round-trip: DirectiveMap on the slot must still allow the hub.
            let slot_csp = slot.as_ref().unwrap().to_string();
            assert!(csp_connect_allows(&slot_csp, "http://10.0.2.100:8787").unwrap());
        });
    }

    #[test]
    fn launch_authorized_hub_alone_still_lands_in_connect_src() {
        with_policy_env(None, None, || {
            let mut slot: Option<Csp> = Some(Csp::Policy(BASE.to_string()));
            // No policy / compile-time hub — launch hub alone is still folded in.
            let applied = apply_hub_connect_csp_to_config_with_launch(
                &mut slot,
                Some("http://10.0.2.100:8787"),
            )
            .unwrap();
            assert!(csp_connect_allows(&applied.effective_csp, "http://10.0.2.100:8787").unwrap());
            assert!(!csp_connect_allows(&applied.effective_csp, "https://evil.example").unwrap());
        });
    }

    #[test]
    fn html_meta_injection_embeds_authorized_origin_not_evil() {
        let html = r#"<!doctype html><html><head><title>t</title></head><body></body></html>"#;
        let csp = build_csp_with_hub_connect(
            BASE,
            &["http://10.0.2.100:8787".to_string()],
        )
        .unwrap();
        let out = inject_csp_meta_html(html, &csp);
        assert!(out.contains("http-equiv=\"Content-Security-Policy\""));
        assert!(out.contains("http://10.0.2.100:8787"));
        assert!(!out.contains("evil.example"));
        assert!(!out.contains("http: ") && !out.contains("connect-src http:"));
        // Replacing an existing meta keeps a single tag with the new policy.
        let again = inject_csp_meta_html(&out, &csp);
        assert_eq!(
            again.matches("Content-Security-Policy").count(),
            1,
            "expected a single CSP meta after re-inject"
        );
    }
}
