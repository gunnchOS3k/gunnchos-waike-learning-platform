import type { TrustStatus } from "../lib/types";

export function TrustBanner({ trust }: { trust: TrustStatus }) {
  const label = trust.trusted ? "Verified learner pack" : "Not trusted";
  const tone = trust.trusted ? "ok" : "warn";
  return (
    <div
      className={`trust-banner trust-${tone}`}
      role="status"
      aria-live="polite"
      data-testid="trust-banner"
    >
      <span className="trust-dot" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <p>
          {trust.trusted
            ? `${trust.module_id} · ${trust.verification_status}`
            : trust.reason ?? trust.verification_status}
        </p>
      </div>
    </div>
  );
}
