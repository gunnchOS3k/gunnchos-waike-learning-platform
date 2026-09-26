import type { SchoolApp } from "./types";

export function validateSchoolAppLaunch(app: SchoolApp, requestedUrl: string): { ok: boolean; reason?: string } {
  if (app.captures_credentials !== false) {
    return { ok: false, reason: "WAIKE_MUST_NOT_CAPTURE_CREDENTIALS" };
  }
  if (app.configured_by !== "institution") {
    return { ok: false, reason: "NOT_INSTITUTION_CONFIGURED" };
  }
  let parsed: URL;
  try {
    parsed = new URL(requestedUrl);
  } catch {
    return { ok: false, reason: "INVALID_URL" };
  }
  if (!["https:", "http:"].includes(parsed.protocol)) {
    return { ok: false, reason: "PROTOCOL_DENIED" };
  }
  const origin = parsed.origin;
  if (!app.allowed_origins.includes(origin)) {
    return { ok: false, reason: "ORIGIN_DENIED" };
  }
  if (requestedUrl !== app.url && !requestedUrl.startsWith(`${app.url}`)) {
    return { ok: false, reason: "URL_NOT_CONFIGURED" };
  }
  return { ok: true };
}

export function exampleSchoolAppsConfig(): SchoolApp[] {
  return [
    {
      app_id: "institution.portal",
      label: "School portal",
      launch_kind: "browser_url",
      url: "https://portal.example.edu/apps",
      allowed_origins: ["https://portal.example.edu"],
      pinned: true,
      configured_by: "institution",
      captures_credentials: false,
    },
  ];
}
