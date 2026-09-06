export type DeviceProfile = {
  id: string;
  name: string;
  research_role: string;
  companion_only?: boolean;
};

export function DeviceProfilePanel({ profiles }: { profiles: DeviceProfile[] }) {
  return (
    <section aria-labelledby="device-profiles-heading">
      <h2 id="device-profiles-heading">Device Quartet (digital)</h2>
      <p>Synthetic capability profiles. Physical validation is external.</p>
      <ul>
        {profiles.map((p) => (
          <li key={p.id} tabIndex={0}>
            <strong>{p.name}</strong> — {p.research_role}
            {p.companion_only ? " (companion)" : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
