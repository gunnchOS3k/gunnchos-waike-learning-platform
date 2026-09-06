/**
 * In-process stand-in for the native store, enforcing the same invariants as
 * `src-tauri/src/offline.rs` (min id length, no client-set `acknowledged`, ack
 * requires a receipt, acknowledged is terminal). The Rust tests prove the native
 * side; this proves the coordinator obeys the contract without a Tauri runtime.
 *
 * `snapshot()`/`restore()` model process restart: the durable rows survive, the
 * coordinator instance does not.
 */

import type {
  CachedLease,
  NativeOfflineStore,
  OfflineState,
  SyncCounts,
  SyncOutboxItem,
  SyncStatus,
} from "../../lib/tauriBridge";

const STATUSES: SyncStatus[] = [
  "pending",
  "syncing",
  "acknowledged",
  "conflict",
  "rejected",
  "retryable_error",
  "quarantined",
];

const CLIENT_SETTABLE: SyncStatus[] = [
  "pending",
  "syncing",
  "conflict",
  "rejected",
  "retryable_error",
  "quarantined",
];

const OUTSTANDING: SyncStatus[] = ["pending", "syncing", "retryable_error"];

export interface StoreSnapshot {
  items: SyncOutboxItem[];
  leases: Array<CachedLease & { cached_at: string }>;
}

export class MemoryOfflineStore implements NativeOfflineStore {
  private items = new Map<string, SyncOutboxItem>();
  private leases = new Map<string, CachedLease & { cached_at: string }>();

  snapshot(): StoreSnapshot {
    return JSON.parse(
      JSON.stringify({ items: [...this.items.values()], leases: [...this.leases.values()] }),
    ) as StoreSnapshot;
  }

  static restore(snap: StoreSnapshot): MemoryOfflineStore {
    const s = new MemoryOfflineStore();
    for (const i of snap.items) s.items.set(i.client_mutation_id, { ...i });
    for (const l of snap.leases) s.leases.set(l.lease_id, { ...l });
    return s;
  }

  async cacheLease(lease: CachedLease, cachedAt: string): Promise<void> {
    if (!lease.lease_id) throw new Error("lease_id required");
    if (!lease.section_id) throw new Error("section_id required");
    this.leases.set(lease.lease_id, { ...lease, cached_at: cachedAt });
  }

  async getLease(sectionId: string): Promise<CachedLease | null> {
    const found = [...this.leases.values()]
      .filter((l) => l.section_id === sectionId)
      .sort((a, b) => (a.cached_at < b.cached_at ? 1 : -1));
    return found[0] ?? null;
  }

  async listLeases(): Promise<CachedLease[]> {
    return [...this.leases.values()];
  }

  async markLeaseRevoked(leaseId: string, reason: string): Promise<void> {
    const l = this.leases.get(leaseId);
    if (!l) throw new Error("lease not found");
    l.revoked = true;
    l.revoke_reason = reason;
  }

  async markLeaseExpired(leaseId: string, expiredAt: string): Promise<void> {
    const l = this.leases.get(leaseId);
    if (!l) throw new Error("lease not found");
    l.expires_at = expiredAt;
  }

  async enqueueMutation(item: SyncOutboxItem): Promise<void> {
    if (item.client_mutation_id.length < 8) throw new Error("client_mutation_id too short");
    if (!CLIENT_SETTABLE.includes(item.sync_status)) {
      throw new Error(`status not client-settable: ${item.sync_status}`);
    }
    if (this.items.has(item.client_mutation_id)) return; // idempotent enqueue
    this.items.set(item.client_mutation_id, { ...item });
  }

  async nextLocalSequence(): Promise<number> {
    return (
      [...this.items.values()].reduce((max, i) => Math.max(max, i.local_sequence), 0) + 1
    );
  }

  async listPending(): Promise<SyncOutboxItem[]> {
    return [...this.items.values()]
      .filter((i) => OUTSTANDING.includes(i.sync_status))
      .sort((a, b) => a.local_sequence - b.local_sequence)
      .map((i) => ({ ...i }));
  }

  async listByStatus(status: SyncStatus): Promise<SyncOutboxItem[]> {
    if (!STATUSES.includes(status)) throw new Error(`unknown status: ${status}`);
    return [...this.items.values()]
      .filter((i) => i.sync_status === status)
      .sort((a, b) => a.local_sequence - b.local_sequence)
      .map((i) => ({ ...i }));
  }

  async updateMutationState(
    id: string,
    status: Exclude<SyncStatus, "acknowledged">,
    lastError: string | null,
    updatedAt: string,
  ): Promise<void> {
    if (!CLIENT_SETTABLE.includes(status)) throw new Error(`status not client-settable: ${status}`);
    const row = this.items.get(id);
    if (!row) throw new Error("mutation not found");
    if (row.sync_status === "acknowledged") throw new Error("acknowledged is terminal");
    row.sync_status = status;
    row.last_error = lastError;
    row.updated_at = updatedAt;
    row.attempt_count += 1;
  }

  async persistAck(id: string, receiptJson: string, ackPersistedAt: string): Promise<void> {
    const row = this.items.get(id);
    if (!row) throw new Error("mutation not found");
    if (!receiptJson.trim()) throw new Error("receipt required");
    if (!ackPersistedAt.trim()) throw new Error("ack timestamp required");
    JSON.parse(receiptJson); // must be a real receipt, not a placeholder
    row.ack_receipt_json = receiptJson;
    row.ack_persisted_at = ackPersistedAt;
    row.sync_status = "acknowledged";
    row.updated_at = ackPersistedAt;
  }

  async getCounts(): Promise<SyncCounts> {
    const rows = [...this.items.values()];
    const by = (s: SyncStatus) => rows.filter((r) => r.sync_status === s).length;
    return {
      pending: by("pending"),
      syncing: by("syncing"),
      acknowledged: by("acknowledged"),
      conflict: by("conflict"),
      rejected: by("rejected"),
      retryable_error: by("retryable_error"),
      quarantined: by("quarantined"),
      ack_persisted: rows.filter((r) => r.ack_receipt_json && r.ack_persisted_at).length,
      acknowledged_without_receipt: rows.filter(
        (r) => r.sync_status === "acknowledged" && !(r.ack_receipt_json && r.ack_persisted_at),
      ).length,
    };
  }

  async offlineState(sectionId?: string | null): Promise<OfflineState> {
    const counts = await this.getCounts();
    const lease = sectionId ? await this.getLease(sectionId) : null;
    const usable = Boolean(
      lease && !lease.revoked && Date.parse(lease.expires_at) > Date.now(),
    );
    const outstanding = counts.pending + counts.syncing + counts.retryable_error;
    return {
      counts,
      outstanding,
      needs_attention: counts.conflict + counts.rejected + counts.quarantined,
      all_work_acknowledged:
        outstanding === 0 &&
        counts.conflict + counts.rejected + counts.quarantined === 0 &&
        counts.acknowledged_without_receipt === 0,
      lease_usable: usable,
      lease_expires_at: lease?.expires_at ?? null,
      lease_revoke_reason: lease?.revoke_reason ?? null,
    };
  }
}
