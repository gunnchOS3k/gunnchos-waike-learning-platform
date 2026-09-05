/**
 * Coordinator against a real hub process over HTTP. No fetch mocks, no fake
 * receipts: every assertion below reflects what the server actually returned.
 */

import { beforeAll, describe, expect, it } from "vitest";
import { SyncCoordinator, deriveUxFromState } from "../../lib/offline/syncCoordinator";
import { MemoryOfflineStore } from "./memoryOfflineStore";
import { SECTION, SITE, liveTransport, login, mutationId, type LiveSession } from "./liveHub";

let learner: LiveSession;
let assignmentId: string;

/** A real section in another site the alpha learner has no business touching. */
const OTHER_SECTION = "sec_beta_dc_w01";

function makeCoordinator(
  store: MemoryOfflineStore,
  session: LiveSession,
  opts: { deviceId?: string; online?: () => boolean } = {},
) {
  return new SyncCoordinator({
    store,
    transport: liveTransport(session),
    deviceId: opts.deviceId ?? "device-live-1",
    siteId: SITE,
    isOnline: opts.online ?? (() => true),
  });
}

beforeAll(async () => {
  learner = await login("learner-alpha");
  const assignments = await learner.req<Array<{ assignment_id: string }>>("/api/v1/assignments");
  expect(assignments.length).toBeGreaterThan(0);
  assignmentId = assignments[0].assignment_id;
});

describe("lease lifecycle against the live hub", () => {
  it("stores a server-issued lease natively and reports it usable", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner);
    const lease = await coord.acquireLease(SECTION);

    expect(lease.lease_id).toMatch(/^lease/);
    expect(lease.section_id).toBe(SECTION);
    expect(lease.capabilities.length).toBeGreaterThan(0);
    expect(lease.revoked).toBe(false);

    const state = await coord.state(SECTION);
    expect(state.leaseUsable).toBe(true);
    expect(state.ux).toBe("online");
  });

  it("records instructor revocation and stops claiming a usable lease", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-revoke-1" });
    const lease = await coord.acquireLease(SECTION);

    const instructor = await login("instructor-alpha");
    await instructor.req(`/api/v1/sync/leases/${lease.lease_id}/revoke`, {
      method: "POST",
      body: JSON.stringify({ reason: "device_lost" }),
    });

    const refreshed = await coord.refreshLease(SECTION);
    expect(refreshed?.revoked).toBe(true);
    const state = await coord.state(SECTION);
    expect(state.leaseUsable).toBe(false);
    expect(state.leaseRevokeReason).toBeTruthy();
  });
});

describe("offline queue drains through the real sync endpoint", () => {
  it("moves pending → syncing → acknowledged only after the receipt is stored", async () => {
    const store = new MemoryOfflineStore();
    const observed: string[] = [];
    const coord = new SyncCoordinator({
      store,
      transport: liveTransport(learner),
      deviceId: "device-drain-1",
      siteId: SITE,
      isOnline: () => true,
      onStateChange: (s) => observed.push(s.ux),
    });
    await coord.acquireLease(SECTION);

    const id = mutationId("drain");
    await coord.enqueue({
      clientMutationId: id,
      sectionId: SECTION,
      entityType: "lesson_progress",
      entityId: "L1",
      operation: "upsert",
      payload: { pack_id: "pack_dc", lesson_id: "L1", percent_complete: 55 },
    });

    // Before the flush the banner must not read as synced.
    let state = await coord.state(SECTION);
    expect(state.ux).toBe("pending");
    expect(state.allWorkAcknowledged).toBe(false);

    const outcome = await coord.flush();
    expect(outcome.attempted).toBe(1);
    expect(outcome.acknowledged).toBe(1);
    expect(outcome.conflicts).toEqual([]);
    expect(outcome.rejected).toEqual([]);

    const row = (await store.listByStatus("acknowledged"))[0];
    expect(row.client_mutation_id).toBe(id);
    expect(row.ack_persisted_at).toBeTruthy();
    // The stored receipt is the server's, not a locally invented one.
    const receipt = JSON.parse(row.ack_receipt_json!) as Record<string, unknown>;
    expect(receipt.client_mutation_id).toBe(id);

    state = await coord.state(SECTION);
    expect(state.ux).toBe("synced");
    expect(state.allWorkAcknowledged).toBe(true);
    expect(state.counts.acknowledged_without_receipt).toBe(0);
    expect(observed).toContain("syncing");
  });

  it("queues while offline and delivers everything in order once back online", async () => {
    const store = new MemoryOfflineStore();
    let online = false;
    const coord = makeCoordinator(store, learner, {
      deviceId: "device-offline-1",
      online: () => online,
    });

    const ids = [mutationId("off_a"), mutationId("off_b"), mutationId("off_c")];
    for (const [i, id] of ids.entries()) {
      await coord.enqueue({
        clientMutationId: id,
        sectionId: SECTION,
        entityType: "lesson_progress",
        entityId: `L${i + 2}`,
        operation: "upsert",
        payload: { pack_id: "pack_dc", lesson_id: `L${i + 2}`, percent_complete: 10 * (i + 1) },
      });
    }

    const blocked = await coord.flush();
    expect(blocked.offline).toBe(true);
    expect(blocked.attempted).toBe(0);
    expect((await coord.state(SECTION)).ux).toBe("offline");

    online = true;
    const outcome = await coord.flush();
    expect(outcome.acknowledged).toBe(3);
    const acked = await store.listByStatus("acknowledged");
    expect(acked.map((a) => a.client_mutation_id)).toEqual(ids);
    expect(acked.every((a) => a.ack_persisted_at)).toBe(true);
  });

  it("replays a duplicate mutation id idempotently instead of double-applying", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-idem-1" });
    const id = mutationId("idem");
    const payload = { pack_id: "pack_dc", lesson_id: "L7", percent_complete: 33 };

    await coord.enqueue({
      clientMutationId: id,
      sectionId: SECTION,
      entityType: "lesson_progress",
      entityId: "L7",
      operation: "upsert",
      payload,
    });
    await coord.flush();
    const first = JSON.parse((await store.listByStatus("acknowledged"))[0].ack_receipt_json!);

    // Same id, same payload, sent again exactly as a retry would.
    const replay = await liveTransport(learner).applyMutation({
      client_mutation_id: id,
      site_id: SITE,
      section_id: SECTION,
      device_id: "device-idem-1",
      entity_type: "lesson_progress",
      entity_id: "L7",
      base_revision: 0,
      operation: "upsert",
      payload,
      local_sequence: 1,
    });
    expect(replay.server_revision).toBe(first.server_revision);
  });
});

describe("restart recovery", () => {
  it("resumes a queue left behind by a killed process", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-restart-1" });
    await coord.acquireLease(SECTION);

    const id = mutationId("restart");
    await coord.enqueue({
      clientMutationId: id,
      sectionId: SECTION,
      entityType: "lesson_progress",
      entityId: "L9",
      operation: "upsert",
      payload: { pack_id: "pack_dc", lesson_id: "L9", percent_complete: 80 },
    });
    // Simulate dying mid-flight: the row is `syncing` with no receipt.
    await store.updateMutationState(id, "syncing", null, new Date().toISOString());

    const persisted = store.snapshot();
    const revived = MemoryOfflineStore.restore(persisted);
    const coord2 = makeCoordinator(revived, learner, { deviceId: "device-restart-1" });

    const resumed = await coord2.resume(SECTION);
    // A stale `syncing` row is never silently treated as delivered.
    expect(resumed.allWorkAcknowledged).toBe(false);
    expect(resumed.outstanding).toBe(1);

    const outcome = await coord2.flush();
    expect(outcome.acknowledged).toBe(1);
    const final = await coord2.state(SECTION);
    expect(final.ux).toBe("synced");
    expect(final.counts.acknowledged_without_receipt).toBe(0);
  });

  it("keeps the cached lease across a restart", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-restart-2" });
    const lease = await coord.acquireLease(SECTION);

    const revived = MemoryOfflineStore.restore(store.snapshot());
    const coord2 = makeCoordinator(revived, learner, { deviceId: "device-restart-2" });
    const state = await coord2.state(SECTION);
    expect(state.leaseUsable).toBe(true);
    expect((await revived.getLease(SECTION))?.lease_id).toBe(lease.lease_id);
  });
});

describe("server verdicts surface as actionable UI states", () => {
  it("marks a stale-base draft write as a conflict and never as synced", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-conflict-1" });
    await coord.acquireLease(SECTION);

    const assignment = assignmentId;
    // Establish revision 1 on the server.
    await coord.enqueue({
      clientMutationId: mutationId("conf_base"),
      sectionId: SECTION,
      entityType: "assignment_draft",
      entityId: assignment,
      operation: "upsert",
      baseRevision: 0,
      payload: { text_response: "first pass" },
    });
    await coord.flush();

    // A second device writes from a base the server has already moved past.
    await coord.enqueue({
      clientMutationId: mutationId("conf_stale"),
      sectionId: SECTION,
      entityType: "assignment_draft",
      entityId: assignment,
      operation: "upsert",
      baseRevision: 0,
      payload: { text_response: "stale device text" },
    });
    const outcome = await coord.flush();

    expect(outcome.conflicts.length).toBe(1);
    const state = await coord.state(SECTION);
    expect(state.ux).toBe("conflict");
    expect(state.allWorkAcknowledged).toBe(false);
    expect(state.needsAttention).toBe(1);
  });

  it("rejects a mutation aimed at a section the learner is not in", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-authz-1" });
    await coord.enqueue({
      clientMutationId: mutationId("authz"),
      sectionId: OTHER_SECTION,
      entityType: "lesson_progress",
      entityId: "L1",
      operation: "upsert",
      payload: { pack_id: "pack_dc", lesson_id: "L1", percent_complete: 5 },
    });

    const outcome = await coord.flush();
    expect(outcome.acknowledged).toBe(0);
    expect(outcome.rejected.length).toBe(1);
    const row = (await store.listByStatus("rejected"))[0];
    expect(row.ack_persisted_at).toBeNull();
    expect((await coord.state()).ux).toBe("rejected");
  });

  it("reports a revoked learner's pull failure instead of showing stale success", async () => {
    const store = new MemoryOfflineStore();
    const coord = makeCoordinator(store, learner, { deviceId: "device-pull-1" });
    const pulled = await coord.pull(SECTION, 0);
    expect(pulled?.section_id).toBe(SECTION);

    await expect(coord.pull(OTHER_SECTION, 0)).rejects.toMatchObject({ status: 403 });
  });
});

describe("banner derivation refuses to over-report success", () => {
  it("never says synced while any receipt is missing", async () => {
    const base = {
      counts: {
        pending: 0,
        syncing: 0,
        acknowledged: 1,
        conflict: 0,
        rejected: 0,
        retryable_error: 0,
        quarantined: 0,
        ack_persisted: 0,
        acknowledged_without_receipt: 1,
      },
      outstanding: 0,
      needs_attention: 0,
      all_work_acknowledged: false,
      lease_usable: true,
      lease_expires_at: null,
      lease_revoke_reason: null,
    };
    expect(deriveUxFromState(base, { online: true, syncing: false })).toBe("pending");
    expect(deriveUxFromState(base, { online: false, syncing: false })).toBe("offline");
  });
});
