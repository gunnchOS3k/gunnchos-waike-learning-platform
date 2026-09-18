/**
 * Web IndexedDB offline store adapter.
 * Explicitly unsupported for durable exact-once sync until Phase B earns it.
 * Callers must treat getWebOfflineStore() === null as honesty, not silent mock.
 */

import type { NativeOfflineStore } from "../lib/tauriBridge";

export function getWebOfflineStore(): NativeOfflineStore | null {
  // Do not invent a durable queue that cannot meet Tauri exact-once guarantees.
  return null;
}

export function webOfflineSupportStatus(): {
  supported: false;
  reason: string;
} {
  return {
    supported: false,
    reason: "WEB_INDEXEDDB_OFFLINE_NOT_CLAIMED",
  };
}
