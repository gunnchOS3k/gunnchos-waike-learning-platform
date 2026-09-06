import { SYNC_UX_LABELS, type SyncUxState } from "../../lib/offline/syncUx";

export function SyncStatusBanner({ state }: { state: SyncUxState }) {
  return (
    <div
      className="sync-status-banner"
      role="status"
      aria-live="polite"
      data-sync-state={state}
    >
      <span className="sync-status-label">{SYNC_UX_LABELS[state]}</span>
    </div>
  );
}
