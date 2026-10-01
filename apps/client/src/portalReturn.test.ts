import { describe, expect, it } from "vitest";
import { portalReturnHref } from "./portalReturn";

describe("portal return", () => {
  it("accepts an http(s) gateway and strips a trailing slash", () => {
    expect(portalReturnHref("https://gunnchos-site.gunnchos-finds.workers.dev/")).toBe(
      "https://gunnchos-site.gunnchos-finds.workers.dev",
    );
    expect(portalReturnHref("https://gunnchos.com")).toBe("https://gunnchos.com");
  });

  it("rejects missing and non-http values", () => {
    expect(portalReturnHref(undefined)).toBeNull();
    expect(portalReturnHref("  ")).toBeNull();
    expect(portalReturnHref("javascript:alert(1)")).toBeNull();
  });
});
