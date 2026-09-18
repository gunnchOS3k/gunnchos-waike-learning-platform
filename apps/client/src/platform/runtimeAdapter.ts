/** Runtime platform detection for Tauri desktop vs Pixel Chrome/PWA web. */

export type RuntimeKind = "TAURI_DESKTOP" | "WEB_MOBILE" | "WEB_DESKTOP";

export type Capability =
  | "native_offline_store"
  | "pack_install_dialog"
  | "deviceos_launch_context"
  | "pwa_install"
  | "touch_nav"
  | "web_indexeddb_offline";

export interface RuntimeAdapter {
  kind: RuntimeKind;
  isTouchPrimary: boolean;
  isStandaloneDisplay: boolean;
  capabilities: Record<Capability, boolean | "unsupported">;
  /** Honest label for pilot banner — never claims mock Hub. */
  pilotBannerLabel: string;
}

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function isStandaloneDisplay(): boolean {
  if (typeof window === "undefined") return false;
  const mq = window.matchMedia?.("(display-mode: standalone)")?.matches;
  const ios = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return Boolean(mq || ios);
}

function isTouchPrimary(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(pointer: coarse)")?.matches ?? false;
}

function isNarrow(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(max-width: 860px)")?.matches ?? false;
}

/**
 * Resolve the active runtime. Web never silently pretends to be Tauri.
 * Tauri-only capabilities are marked unsupported on web — not mocked.
 */
export function detectRuntime(env: {
  MODE?: string;
  VITE_PIXEL_PILOT?: string;
} = import.meta.env): RuntimeAdapter {
  const pilot =
    String(env.VITE_PIXEL_PILOT || "").toLowerCase() === "true" ||
    String(env.VITE_PIXEL_PILOT || "") === "1";

  if (isTauri()) {
    return {
      kind: "TAURI_DESKTOP",
      isTouchPrimary: false,
      isStandaloneDisplay: true,
      capabilities: {
        native_offline_store: true,
        pack_install_dialog: true,
        deviceos_launch_context: true,
        pwa_install: "unsupported",
        touch_nav: false,
        web_indexeddb_offline: "unsupported",
      },
      pilotBannerLabel: pilot ? "Pixel pilot · Tauri desktop" : "Tauri desktop",
    };
  }

  const mobile = isTouchPrimary() || isNarrow() || pilot;
  return {
    kind: mobile ? "WEB_MOBILE" : "WEB_DESKTOP",
    isTouchPrimary: isTouchPrimary() || pilot,
    isStandaloneDisplay: isStandaloneDisplay(),
    capabilities: {
      native_offline_store: "unsupported",
      pack_install_dialog: "unsupported",
      deviceos_launch_context: "unsupported",
      pwa_install: true,
      touch_nav: true,
      // IndexedDB offline queue is Phase-B honesty: not claimed as durable yet.
      web_indexeddb_offline: false,
    },
    pilotBannerLabel: pilot
      ? "Pixel 6a pilot · web/PWA · password auth · real Hub"
      : "Web client",
  };
}

export function capabilitySupported(adapter: RuntimeAdapter, cap: Capability): boolean {
  return adapter.capabilities[cap] === true;
}
