import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function browseInstallPack(): Promise<string | null> {
  if (!isTauri()) return null;
  const selected = await open({
    directory: true,
    multiple: false,
    title: "Select verified learner pack directory",
  });
  if (!selected || Array.isArray(selected)) return null;
  return selected;
}

// --- Gate A: native offline store --------------------------------------------

export type SyncStatus =
  | "pending"
  | "syncing"
  | "acknowledged"
  | "conflict"
  | "rejected"
  | "retryable_error"
  | "quarantined";

export interface CachedLease {
  lease_id: string;
  user_id: string;
  site_id: string;
  section_id: string;
  device_id: string;
  issued_at: string;
  expires_at: string;
  capabilities: string[];
  revoked: boolean;
  revoke_reason: string | null;
}

export interface SyncOutboxItem {
  client_mutation_id: string;
  section_id: string;
  entity_type: string;
  entity_id: string;
  base_revision: number;
  operation: string;
  payload_json: string;
  local_sequence: number;
  sync_status: SyncStatus;
  created_at: string;
  updated_at: string;
  attempt_count: number;
  last_error: string | null;
  ack_receipt_json: string | null;
  ack_persisted_at: string | null;
}

export interface SyncCounts {
  pending: number;
  syncing: number;
  acknowledged: number;
  conflict: number;
  rejected: number;
  retryable_error: number;
  quarantined: number;
  ack_persisted: number;
  acknowledged_without_receipt: number;
}

export interface OfflineState {
  counts: SyncCounts;
  outstanding: number;
  needs_attention: number;
  all_work_acknowledged: boolean;
  lease_usable: boolean;
  lease_expires_at: string | null;
  lease_revoke_reason: string | null;
}

/**
 * Durable offline store. Every method is a typed Tauri command; the webview has no
 * way to send SQL, a table name, or a column name across this boundary.
 */
export interface NativeOfflineStore {
  cacheLease(lease: CachedLease, cachedAt: string): Promise<void>;
  getLease(sectionId: string): Promise<CachedLease | null>;
  listLeases(): Promise<CachedLease[]>;
  markLeaseRevoked(leaseId: string, reason: string): Promise<void>;
  markLeaseExpired(leaseId: string, expiredAt: string): Promise<void>;
  enqueueMutation(item: SyncOutboxItem): Promise<void>;
  nextLocalSequence(): Promise<number>;
  listPending(): Promise<SyncOutboxItem[]>;
  listByStatus(status: SyncStatus): Promise<SyncOutboxItem[]>;
  updateMutationState(
    clientMutationId: string,
    status: Exclude<SyncStatus, "acknowledged">,
    lastError: string | null,
    updatedAt: string,
  ): Promise<void>;
  persistAck(clientMutationId: string, receiptJson: string, ackPersistedAt: string): Promise<void>;
  getCounts(): Promise<SyncCounts>;
  offlineState(sectionId?: string | null): Promise<OfflineState>;
}

export const nativeOfflineStore: NativeOfflineStore = {
  cacheLease: (lease, cachedAt) => invoke("sync_cache_lease", { lease, cachedAt }),
  getLease: (sectionId) => invoke("sync_get_lease", { sectionId }),
  listLeases: () => invoke("sync_list_leases"),
  markLeaseRevoked: (leaseId, reason) => invoke("sync_mark_lease_revoked", { leaseId, reason }),
  markLeaseExpired: (leaseId, expiredAt) => invoke("sync_mark_lease_expired", { leaseId, expiredAt }),
  enqueueMutation: (item) => invoke("sync_enqueue_mutation", { item }),
  nextLocalSequence: () => invoke("sync_next_local_sequence"),
  listPending: () => invoke("sync_list_pending"),
  listByStatus: (status) => invoke("sync_list_by_status", { status }),
  updateMutationState: (clientMutationId, status, lastError, updatedAt) =>
    invoke("sync_update_mutation_state", { clientMutationId, status, lastError, updatedAt }),
  persistAck: (clientMutationId, receiptJson, ackPersistedAt) =>
    invoke("sync_persist_ack", { clientMutationId, receiptJson, ackPersistedAt }),
  getCounts: () => invoke("sync_get_counts"),
  offlineState: (sectionId) => invoke("sync_offline_state", { sectionId: sectionId ?? null }),
};

export function getOfflineStore(): NativeOfflineStore | null {
  return isTauri() ? nativeOfflineStore : null;
}

/** Device OS deep-link navigation intent (one-shot; never authenticates). */
export interface DeviceOsDeepLink {
  uri: string;
  canonical: string;
  kind: string;
  path: string;
  segments: string[];
  valid: boolean;
}

export interface DeviceOsLaunchContext {
  protocol: string;
  request_id: string;
  bundle_id: string;
  deep_link: DeviceOsDeepLink;
  context: Record<string, unknown>;
  app_version: string;
  consumed: boolean;
}

export async function getInitialDeviceOsLaunchContext(): Promise<DeviceOsLaunchContext | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<DeviceOsLaunchContext | null>("get_initial_deviceos_launch_context");
  } catch {
    return null;
  }
}

/** Map Device OS deep-link kinds onto existing authenticated UI modes. */
export function modeForDeviceOsDeepLink(kind: string): string | null {
  switch (kind) {
    case "learn":
    case "section":
    case "sync":
      return "home";
    case "quiz":
    case "assignment":
      return "assignments";
    case "device":
      return "interop";
    default:
      return null;
  }
}
