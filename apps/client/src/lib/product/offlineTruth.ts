export interface OfflineTruth {
  downloaded: string[];
  available_offline: string[];
  queued_changes: number;
  awaiting_sync: number;
  needs_internet: string[];
  conflict_attention: string[];
  stale_as_current: false;
  durable: boolean;
  pin_supported: boolean;
}

export function buildOfflineTruth(args: {
  downloaded?: string[];
  availableOffline?: string[];
  queuedChanges?: number;
  awaitingSync?: number;
  needsInternet?: string[];
  conflicts?: string[];
  durable: boolean;
  pinSupported: boolean;
}): OfflineTruth {
  return {
    downloaded: args.downloaded || [],
    available_offline: args.availableOffline || [],
    queued_changes: args.queuedChanges || 0,
    awaiting_sync: args.awaitingSync || 0,
    needs_internet: args.needsInternet || [],
    conflict_attention: args.conflicts || [],
    stale_as_current: false,
    durable: args.durable,
    pin_supported: args.pinSupported,
  };
}
