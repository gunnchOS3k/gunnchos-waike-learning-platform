export function AdminHardeningPanel({
  workflows,
}: {
  workflows: string[];
}) {
  return (
    <section aria-labelledby="admin-hardening-heading">
      <h2 id="admin-hardening-heading">Admin / hardening</h2>
      <nav aria-label="Admin workflows">
        <ul>
          {workflows.map((w) => (
            <li key={w}>
              <button type="button">{w.replaceAll("_", " ")}</button>
            </li>
          ))}
        </ul>
      </nav>
    </section>
  );
}
