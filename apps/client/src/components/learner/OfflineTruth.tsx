import type { OfflineTruth } from "../../lib/product/offlineTruth";

export function OfflineTruthPanel({ truth }: { truth: OfflineTruth }) {
  return (
    <section className="panel" data-testid="offline-truth">
      <h2>Offline</h2>
      <p className="muted">
        {truth.durable
          ? "This device keeps a durable queue."
          : "This browser session does not claim a durable offline store."}
      </p>
      <ul>
        <li>Downloaded: {truth.downloaded.length ? truth.downloaded.join(", ") : "none yet"}</li>
        <li>Available offline: {truth.available_offline.length ? truth.available_offline.join(", ") : "none"}</li>
        <li>Queued changes: {truth.queued_changes}</li>
        <li>Awaiting sync: {truth.awaiting_sync}</li>
        <li>Needs internet: {truth.needs_internet.length ? truth.needs_internet.join(", ") : "none listed"}</li>
        <li>Needs your attention: {truth.conflict_attention.length ? truth.conflict_attention.join(", ") : "none"}</li>
      </ul>
      <p className="muted">Stale copies are never shown as current.</p>
    </section>
  );
}
