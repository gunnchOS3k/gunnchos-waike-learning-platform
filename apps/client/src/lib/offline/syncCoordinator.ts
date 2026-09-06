/**
 * Offline sync coordinator.
 *
 * Ordering rule that the whole feature rests on: a mutation is only marked
 * `acknowledged` after its receipt is durably stored. If the process dies between
 * the server write and the local receipt write, the mutation stays outstanding and
 * is retried; the server's idempotency ledger collapses the duplicate.
 */

import type {
  CachedLease,
  NativeOfflineStore,
  OfflineState,
  SyncCounts,
  SyncOutboxItem,
  SyncStatus,
} from "../tauriBridge";
import type { SyncUxState } from "./syncUx";

export interface LeaseResponse {
  lease_id: string;
  user_id?: string;
  site_id: string;
  section_id: string;
  device_id: string;
  issued_at: string;
  expires_at: string;
  capabilities: string[];
  revoked?: boolean;
  revoke_reason?: string | null;
}

/** The `/sync/mutations` envelope. Domain outcomes live under `result`. */
export interface MutationReceipt {
  client_mutation_id: string;
  sync_status: string;
  idempotent_replay?: boolean;
  server_revision?: number;
  /** True only when the server durably recorded an `acknowledged` receipt. */
  ack_durable?: boolean;
  result?: {
    error?: string;
    status?: number;
    server_snapshot?: unknown;
    quarantine_reason?: string | null;
    [k: string]: unknown;
  };
  receipt?: { receipt_id?: string; result?: string; [k: string]: unknown } | null;
}

export interface PullResult {
  section_id: string;
  since_revision: number;
  latest_revision: number;
  changes: Array<Record<string, unknown>>;
}

/** Minimal hub surface the coordinator needs; the real HubClient satisfies it. */
export interface SyncTransport {
  issueLease(sectionId: string, deviceId: string, ttlHours?: number): Promise<LeaseResponse>;
  getLease(leaseId: string): Promise<LeaseResponse>;
  applyMutation(body: {
    client_mutation_id: string;
    site_id: string;
    section_id: string;
    device_id: string;
    entity_type: string;
    entity_id: string;
    base_revision: number;
    operation: string;
    payload: Record<string, unknown>;
    local_sequence: number;
    lease_id?: string | null;
  }): Promise<MutationReceipt>;
  getReceipt(clientMutationId: string): Promise<MutationReceipt>;
  pullChanges(sectionId: string, sinceRevision: number): Promise<PullResult>;
}

export interface TransportError {
  status?: number;
  detail?: string;
  message?: string;
}

export interface EnqueueRequest {
  clientMutationId: string;
  sectionId: string;
  entityType: string;
  entityId: string;
  operation: string;
  payload: Record<string, unknown>;
  baseRevision?: number;
}

export interface FlushOutcome {
  attempted: number;
  acknowledged: number;
  conflicts: string[];
  rejected: string[];
  quarantined: string[];
  retryable: string[];
  /** Set when the network itself is down; the queue is untouched and still valid. */
  offline: boolean;
}

export interface CoordinatorOptions {
  store: NativeOfflineStore;
  transport: SyncTransport;
  deviceId: string;
  siteId: string;
  now?: () => Date;
  isOnline?: () => boolean;
  onStateChange?: (state: CoordinatorState) => void;
}

export interface CoordinatorState {
  ux: SyncUxState;
  counts: SyncCounts;
  outstanding: number;
  needsAttention: number;
  allWorkAcknowledged: boolean;
  leaseUsable: boolean;
  leaseExpiresAt: string | null;
  leaseRevokeReason: string | null;
  syncing: boolean;
  online: boolean;
  lastError: string | null;
}

/** Server statuses that mean "the server made a decision", vs. transport trouble. */
const TERMINAL_SERVER_STATUSES = new Set(["conflict", "rejected", "quarantined"]);

function isNetworkFailure(err: unknown): boolean {
  const e = err as TransportError;
  // A missing/0/5xx status is infrastructure; an explicit 4xx is a server verdict.
  if (typeof e?.status === "number") return e.status >= 500;
  return true;
}

function errorText(err: unknown): string {
  const e = err as TransportError;
  return e?.detail || e?.message || String(err);
}

export class SyncCoordinator {
  private readonly store: NativeOfflineStore;
  private readonly transport: SyncTransport;
  private readonly deviceId: string;
  private readonly siteId: string;
  private readonly now: () => Date;
  private readonly onlineProbe: () => boolean;
  private readonly onStateChange?: (state: CoordinatorState) => void;
  private syncing = false;
  private lastError: string | null = null;
  private inFlight: Promise<FlushOutcome> | null = null;

  constructor(opts: CoordinatorOptions) {
    this.store = opts.store;
    this.transport = opts.transport;
    this.deviceId = opts.deviceId;
    this.siteId = opts.siteId;
    this.now = opts.now ?? (() => new Date());
    this.onlineProbe =
      opts.isOnline ?? (() => (typeof navigator === "undefined" ? true : navigator.onLine));
    this.onStateChange = opts.onStateChange;
  }

  private iso(): string {
    return this.now().toISOString();
  }

  /** Acquire a lease while online and cache it natively for the offline window. */
  async acquireLease(sectionId: string, ttlHours = 72): Promise<CachedLease> {
    const res = await this.transport.issueLease(sectionId, this.deviceId, ttlHours);
    const lease = toCachedLease(res);
    await this.store.cacheLease(lease, this.iso());
    await this.emit();
    return lease;
  }

  /** Re-check a cached lease against the server and record revocation locally. */
  async refreshLease(sectionId: string): Promise<CachedLease | null> {
    const cached = await this.store.getLease(sectionId);
    if (!cached) return null;
    try {
      const fresh = await this.transport.getLease(cached.lease_id);
      if (fresh.revoked) {
        await this.store.markLeaseRevoked(cached.lease_id, fresh.revoke_reason || "revoked");
      } else {
        await this.store.cacheLease(toCachedLease(fresh), this.iso());
      }
    } catch (err) {
      const e = err as TransportError;
      // 403/404 on a lease we hold means it is no longer ours to use.
      if (e?.status === 403 || e?.status === 404) {
        await this.store.markLeaseRevoked(cached.lease_id, errorText(err));
      } else if (!isNetworkFailure(err)) {
        throw err;
      }
    }
    const out = await this.store.getLease(sectionId);
    await this.emit();
    return out;
  }

  /** Queue work locally. Safe with no network and no lease refresh. */
  async enqueue(req: EnqueueRequest): Promise<SyncOutboxItem> {
    const seq = await this.store.nextLocalSequence();
    const stamp = this.iso();
    const item: SyncOutboxItem = {
      client_mutation_id: req.clientMutationId,
      section_id: req.sectionId,
      entity_type: req.entityType,
      entity_id: req.entityId,
      base_revision: req.baseRevision ?? 0,
      operation: req.operation,
      payload_json: JSON.stringify(req.payload),
      local_sequence: seq,
      sync_status: "pending",
      created_at: stamp,
      updated_at: stamp,
      attempt_count: 0,
      last_error: null,
      ack_receipt_json: null,
      ack_persisted_at: null,
    };
    await this.store.enqueueMutation(item);
    await this.emit();
    return item;
  }

  /** Drain the outbox in local sequence order. Concurrent calls share one pass. */
  async flush(): Promise<FlushOutcome> {
    if (this.inFlight) return this.inFlight;
    this.inFlight = this.flushOnce().finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }

  private async flushOnce(): Promise<FlushOutcome> {
    const outcome: FlushOutcome = {
      attempted: 0,
      acknowledged: 0,
      conflicts: [],
      rejected: [],
      quarantined: [],
      retryable: [],
      offline: false,
    };
    if (!this.onlineProbe()) {
      outcome.offline = true;
      await this.emit();
      return outcome;
    }

    const pending = await this.store.listPending();
    if (pending.length === 0) {
      await this.emit();
      return outcome;
    }

    this.syncing = true;
    this.lastError = null;
    await this.emit();
    try {
      for (const item of pending) {
        outcome.attempted += 1;
        await this.store.updateMutationState(item.client_mutation_id, "syncing", null, this.iso());
        await this.emit();
        const settled = await this.deliver(item, outcome);
        if (settled === "offline") {
          outcome.offline = true;
          break;
        }
      }
    } finally {
      this.syncing = false;
      await this.emit();
    }
    return outcome;
  }

  private async deliver(
    item: SyncOutboxItem,
    outcome: FlushOutcome,
  ): Promise<"settled" | "offline"> {
    let receipt: MutationReceipt;
    try {
      receipt = await this.transport.applyMutation({
        client_mutation_id: item.client_mutation_id,
        site_id: this.siteId,
        section_id: item.section_id,
        device_id: this.deviceId,
        entity_type: item.entity_type,
        entity_id: item.entity_id,
        base_revision: item.base_revision,
        operation: item.operation,
        payload: JSON.parse(item.payload_json) as Record<string, unknown>,
        local_sequence: item.local_sequence,
      });
    } catch (err) {
      const e = err as TransportError;
      if (isNetworkFailure(err)) {
        // The server may still have applied it; recover the receipt instead of
        // replaying blindly on the next pass.
        const recovered = await this.recoverReceipt(item.client_mutation_id);
        if (recovered) {
          await this.settle(item, recovered, outcome);
          return "settled";
        }
        this.lastError = errorText(err);
        await this.store.updateMutationState(
          item.client_mutation_id,
          "retryable_error",
          this.lastError,
          this.iso(),
        );
        outcome.retryable.push(item.client_mutation_id);
        return "offline";
      }
      if (e?.status === 409) {
        const detail = errorText(err);
        const status: SyncStatus = detail.includes("MUTATION_ID_REUSE_MISMATCH")
          ? "rejected"
          : "conflict";
        await this.store.updateMutationState(item.client_mutation_id, status, detail, this.iso());
        (status === "rejected" ? outcome.rejected : outcome.conflicts).push(
          item.client_mutation_id,
        );
        return "settled";
      }
      const detail = errorText(err);
      await this.store.updateMutationState(item.client_mutation_id, "rejected", detail, this.iso());
      outcome.rejected.push(item.client_mutation_id);
      return "settled";
    }
    await this.settle(item, receipt, outcome);
    return "settled";
  }

  /**
   * Look up a receipt after an ambiguous send. `/sync/receipts` returns a stored
   * receipt row rather than the mutation envelope, so its `result` field is
   * normalised into the envelope's `sync_status` before the caller acts on it.
   */
  private async recoverReceipt(clientMutationId: string): Promise<MutationReceipt | null> {
    let row: MutationReceipt & { result?: unknown };
    try {
      row = (await this.transport.getReceipt(clientMutationId)) as MutationReceipt & {
        result?: unknown;
      };
    } catch {
      return null;
    }
    if (typeof row.result !== "string") return row;
    const verdict = row.result;
    return {
      client_mutation_id: clientMutationId,
      sync_status: verdict === "ok" ? "acknowledged" : verdict,
      ack_durable: verdict === "ok",
      receipt: row as unknown as MutationReceipt["receipt"],
      result: verdict === "ok" ? {} : { error: verdict },
    };
  }

  private async settle(
    item: SyncOutboxItem,
    receipt: MutationReceipt,
    outcome: FlushOutcome,
  ): Promise<void> {
    const status = String(receipt.sync_status || "");
    if (TERMINAL_SERVER_STATUSES.has(status)) {
      const detail =
        receipt.result?.error || receipt.result?.quarantine_reason || status;
      await this.store.updateMutationState(
        item.client_mutation_id,
        status as Exclude<SyncStatus, "acknowledged">,
        String(detail),
        this.iso(),
      );
      if (status === "conflict") outcome.conflicts.push(item.client_mutation_id);
      else if (status === "rejected") outcome.rejected.push(item.client_mutation_id);
      else outcome.quarantined.push(item.client_mutation_id);
      return;
    }
    if (status !== "acknowledged" || receipt.ack_durable === false) {
      // The server did not durably record this; leave it queued rather than
      // showing the learner a green banner for work that may not have landed.
      await this.store.updateMutationState(
        item.client_mutation_id,
        "retryable_error",
        `ack_not_durable:${status || "unknown"}`,
        this.iso(),
      );
      outcome.retryable.push(item.client_mutation_id);
      return;
    }
    // Receipt first, acknowledged second — the native store enforces this too.
    await this.store.persistAck(
      item.client_mutation_id,
      JSON.stringify(receipt),
      this.iso(),
    );
    outcome.acknowledged += 1;
  }

  async pull(sectionId: string, sinceRevision = 0): Promise<PullResult | null> {
    try {
      return await this.transport.pullChanges(sectionId, sinceRevision);
    } catch (err) {
      const e = err as TransportError;
      if (e?.status === 403) {
        const cached = await this.store.getLease(sectionId);
        if (cached) await this.store.markLeaseRevoked(cached.lease_id, errorText(err));
        await this.emit();
      }
      if (!isNetworkFailure(err)) throw err;
      this.lastError = errorText(err);
      await this.emit();
      return null;
    }
  }

  /** Restart path: adopt whatever the durable queue says without re-deriving it. */
  async resume(sectionId?: string): Promise<CoordinatorState> {
    const stale = await this.store.listByStatus("syncing");
    for (const item of stale) {
      // In-flight at crash time; the outcome is unknown, so recover or retry.
      const recovered = await this.recoverReceipt(item.client_mutation_id);
      if (
        recovered &&
        String(recovered.sync_status) === "acknowledged" &&
        recovered.ack_durable !== false
      ) {
        await this.store.persistAck(
          item.client_mutation_id,
          JSON.stringify(recovered),
          this.iso(),
        );
      } else {
        await this.store.updateMutationState(
          item.client_mutation_id,
          "pending",
          "resumed_after_restart",
          this.iso(),
        );
      }
    }
    return this.state(sectionId);
  }

  async state(sectionId?: string): Promise<CoordinatorState> {
    const snapshot = await this.store.offlineState(sectionId ?? null);
    return this.toState(snapshot);
  }

  private toState(snapshot: OfflineState): CoordinatorState {
    return {
      ux: deriveUxFromState(snapshot, {
        online: this.onlineProbe(),
        syncing: this.syncing,
      }),
      counts: snapshot.counts,
      outstanding: snapshot.outstanding,
      needsAttention: snapshot.needs_attention,
      allWorkAcknowledged: snapshot.all_work_acknowledged,
      leaseUsable: snapshot.lease_usable,
      leaseExpiresAt: snapshot.lease_expires_at,
      leaseRevokeReason: snapshot.lease_revoke_reason,
      syncing: this.syncing,
      online: this.onlineProbe(),
      lastError: this.lastError,
    };
  }

  private async emit(sectionId?: string): Promise<void> {
    if (!this.onStateChange) return;
    this.onStateChange(await this.state(sectionId));
  }
}

/**
 * Maps durable counters to a banner state. `synced` requires an empty outbox *and*
 * a persisted receipt for every acknowledged item, so a torn ack never reads green.
 */
export function deriveUxFromState(
  snapshot: OfflineState,
  ctx: { online: boolean; syncing: boolean },
): SyncUxState {
  if (!ctx.online) return "offline";
  if (ctx.syncing || snapshot.counts.syncing > 0) return "syncing";
  if (snapshot.counts.conflict > 0) return "conflict";
  if (snapshot.counts.rejected > 0) return "rejected";
  if (snapshot.counts.quarantined > 0) return "action_required";
  if (snapshot.counts.retryable_error > 0) return "retryable_failure";
  if (snapshot.counts.pending > 0) return "pending";
  if (snapshot.counts.acknowledged_without_receipt > 0) return "pending";
  if (!snapshot.lease_usable && snapshot.lease_revoke_reason) return "action_required";
  if (snapshot.counts.acknowledged > 0 && snapshot.all_work_acknowledged) return "synced";
  return "online";
}

export function toCachedLease(res: LeaseResponse): CachedLease {
  return {
    lease_id: res.lease_id,
    user_id: res.user_id ?? "",
    site_id: res.site_id,
    section_id: res.section_id,
    device_id: res.device_id,
    issued_at: res.issued_at,
    expires_at: res.expires_at,
    capabilities: res.capabilities ?? [],
    revoked: Boolean(res.revoked),
    revoke_reason: res.revoke_reason ?? null,
  };
}
