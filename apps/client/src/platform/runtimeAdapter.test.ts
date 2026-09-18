import { describe, expect, it } from "vitest";
import { detectRuntime, capabilitySupported } from "./runtimeAdapter";

describe("runtimeAdapter", () => {
  it("marks Tauri-only capabilities unsupported on web", () => {
    const r = detectRuntime({ MODE: "production", VITE_PIXEL_PILOT: "true" });
    expect(r.kind).toBe("WEB_MOBILE");
    expect(r.capabilities.native_offline_store).toBe("unsupported");
    expect(r.capabilities.pack_install_dialog).toBe("unsupported");
    expect(r.capabilities.deviceos_launch_context).toBe("unsupported");
    expect(capabilitySupported(r, "native_offline_store")).toBe(false);
    expect(r.pilotBannerLabel).toMatch(/Pixel 6a pilot/i);
  });

  it("does not enable silent mock hub via adapter", () => {
    const r = detectRuntime({ MODE: "production" });
    expect(JSON.stringify(r)).not.toMatch(/mockHub/i);
  });
});
