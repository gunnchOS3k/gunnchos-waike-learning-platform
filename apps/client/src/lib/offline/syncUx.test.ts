import { describe, expect, it } from "vitest";
import { deriveSyncUx } from "./syncUx";

describe("deriveSyncUx", () => {
  it("never reports synced without durable ack", () => {
    expect(
      deriveSyncUx({
        online: true,
        pendingCount: 0,
        syncing: false,
        lastStatus: "synced",
        ackPersisted: false,
      }),
    ).toBe("online");
  });

  it("reports synced only after ack persistence", () => {
    expect(
      deriveSyncUx({
        online: true,
        pendingCount: 0,
        syncing: false,
        lastStatus: "synced",
        ackPersisted: true,
      }),
    ).toBe("synced");
  });

  it("prefers offline when disconnected", () => {
    expect(
      deriveSyncUx({
        online: false,
        pendingCount: 3,
        syncing: false,
        ackPersisted: false,
      }),
    ).toBe("offline");
  });
});
