import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SyncStatusBanner } from "../components/sync/SyncStatusBanner";
import type { SyncUxState } from "../lib/offline/syncUx";

afterEach(() => {
  cleanup();
});

const STATES: SyncUxState[] = [
  "offline",
  "online",
  "pending",
  "syncing",
  "synced",
  "conflict",
  "action_required",
  "retryable_failure",
  "rejected",
];

describe("Gate A sync UX accessibility smoke (not certification)", () => {
  it.each(STATES)("banner %s exposes polite live status", (state) => {
    render(<SyncStatusBanner state={state} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("data-sync-state", state);
    expect(status.textContent?.length).toBeGreaterThan(0);
  });
});
