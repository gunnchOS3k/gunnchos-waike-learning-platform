import { useEffect, useState } from "react";
import type { HubClient } from "../../lib/hub/client";
import { HubAuthError } from "../../lib/hub/client";

export type InteropMatrix = {
  claim: string;
  supported?: Record<string, boolean>;
  xmlns?: string;
};

export function InteropStatusPanel({
  hub,
  oneroster: onerosterProp,
  qti: qtiProp,
  lti: ltiProp,
}: {
  hub?: HubClient | null;
  oneroster?: InteropMatrix;
  qti?: InteropMatrix;
  lti?: InteropMatrix;
}) {
  const [oneroster, setOneroster] = useState<InteropMatrix>(
    onerosterProp ?? { claim: "loading…" },
  );
  const [qti, setQti] = useState<InteropMatrix>(qtiProp ?? { claim: "loading…" });
  const [lti, setLti] = useState<InteropMatrix>(ltiProp ?? { claim: "loading…" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (onerosterProp) setOneroster(onerosterProp);
    if (qtiProp) setQti(qtiProp);
    if (ltiProp) setLti(ltiProp);
  }, [onerosterProp, qtiProp, ltiProp]);

  useEffect(() => {
    if (!hub) return;
    let cancelled = false;
    (async () => {
      try {
        const [o, q, l] = await Promise.all([
          hub.onerosterMatrix(),
          hub.qtiMatrix(),
          hub.ltiMatrix(),
        ]);
        if (cancelled) return;
        setOneroster(o);
        setQti(q);
        setLti(l);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof HubAuthError ? err.detail : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hub]);

  return (
    <section aria-labelledby="interop-heading" data-testid="interop-status-panel">
      <h2 id="interop-heading">Interoperability (pilot)</h2>
      <p>Digital foundations only — not external certification.</p>
      {error ? (
        <div className="error-box" role="alert" data-testid="interop-error">
          {error}
        </div>
      ) : null}
      <ul>
        <li tabIndex={0} data-testid="interop-oneroster">
          OneRoster: {oneroster.claim}
        </li>
        <li tabIndex={0} data-testid="interop-qti">
          QTI: {qti.claim}
          {qti.xmlns ? ` (${qti.xmlns})` : ""}
        </li>
        <li tabIndex={0} data-testid="interop-lti">
          LTI 1.3: {lti.claim}
        </li>
      </ul>
    </section>
  );
}
