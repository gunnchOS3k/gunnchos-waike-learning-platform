export type InteropMatrix = {
  claim: string;
  supported?: Record<string, boolean>;
};

export function InteropStatusPanel({
  oneroster,
  qti,
  lti,
}: {
  oneroster: InteropMatrix;
  qti: InteropMatrix;
  lti: InteropMatrix;
}) {
  return (
    <section aria-labelledby="interop-heading">
      <h2 id="interop-heading">Interoperability (pilot)</h2>
      <p>Digital foundations only — not external certification.</p>
      <ul>
        <li tabIndex={0}>OneRoster: {oneroster.claim}</li>
        <li tabIndex={0}>QTI: {qti.claim}</li>
        <li tabIndex={0}>LTI 1.3: {lti.claim}</li>
      </ul>
    </section>
  );
}
