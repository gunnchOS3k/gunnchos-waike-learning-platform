import { validateSchoolAppLaunch } from "../../lib/product/schoolApps";
import type { SchoolApp } from "../../lib/product/types";

type Props = {
  apps: SchoolApp[];
  onPin: (appId: string, pinned: boolean) => void;
};

export function SchoolAppsPanel({ apps, onPin }: Props) {
  return (
    <section className="panel" data-testid="school-apps">
      <h2>School apps</h2>
      <p className="muted">
        Opens only apps your school configured. WAIKE does not collect those passwords and does not impersonate other LMS products.
      </p>
      {apps.length === 0 ? (
        <p className="muted">No school apps are configured for this site.</p>
      ) : (
        <ul>
          {apps.map((app) => (
            <li key={app.app_id}>
              <strong>{app.label}</strong>
              <span className="muted"> · {app.launch_kind}</span>
              <div className="toolbar">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    const check = validateSchoolAppLaunch(app, app.url);
                    if (!check.ok) return;
                    window.open(app.url, "_blank", "noopener,noreferrer");
                  }}
                >
                  Open
                </button>
                <button type="button" className="ghost" onClick={() => onPin(app.app_id, !app.pinned)}>
                  {app.pinned ? "Unpin" : "Pin"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
