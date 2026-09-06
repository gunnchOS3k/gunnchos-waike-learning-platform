/** Accessible sync UX states — never show synced before durable ack. */

export type SyncUxState =
  | "offline"
  | "online"
  | "pending"
  | "syncing"
  | "synced"
  | "conflict"
  | "action_required"
  | "retryable_failure"
  | "rejected";

export const SYNC_UX_LABELS: Record<SyncUxState, string> = {
  offline: "Offline",
  online: "Online",
  pending: "Pending sync",
  syncing: "Syncing",
  synced: "Synced",
  conflict: "Conflict — action needed",
  action_required: "Action required",
  retryable_failure: "Sync failed — retry",
  rejected: "Rejected by server",
};

export function deriveSyncUx(args: {
  online: boolean;
  pendingCount: number;
  syncing: boolean;
  lastStatus?: SyncUxState | null;
  ackPersisted: boolean;
}): SyncUxState {
  if (!args.online) return "offline";
  if (args.syncing) return "syncing";
  if (args.lastStatus === "conflict") return "conflict";
  if (args.lastStatus === "rejected") return "rejected";
  if (args.lastStatus === "retryable_failure") return "retryable_failure";
  if (args.lastStatus === "action_required") return "action_required";
  if (args.pendingCount > 0) return "pending";
  // Never display synced before durable server ack persistence.
  if (args.lastStatus === "synced" && args.ackPersisted) return "synced";
  return "online";
}
