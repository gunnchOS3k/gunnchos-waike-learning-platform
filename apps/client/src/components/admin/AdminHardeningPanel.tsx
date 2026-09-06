import { useState } from "react";
import type { HubClient } from "../../lib/hub/client";
import { HubAuthError } from "../../lib/hub/client";

export function AdminHardeningPanel({
  workflows,
  hub,
}: {
  workflows: string[];
  hub: HubClient;
}) {
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [lastBackupPath, setLastBackupPath] = useState<string | null>(null);

  async function run(action: string, fn: () => Promise<unknown>) {
    setBusy(action);
    setError(null);
    setResult(null);
    try {
      const out = await fn();
      setResult(JSON.stringify(out, null, 2));
    } catch (err) {
      setError(err instanceof HubAuthError ? err.detail : String(err));
    } finally {
      setBusy(null);
    }
  }

  function onWorkflow(w: string) {
    switch (w) {
      case "backup_restore":
      case "backup":
        void run("backup", async () => {
          // Enable export for this site before backup (privacy gate).
          await hub.upsertPrivacy({
            youth_mode: false,
            data_minimization: true,
            export_allowed: true,
            retention_days: 365,
          });
          const bak = await hub.createBackup();
          setLastBackupPath(bak.path);
          return bak;
        });
        break;
      case "restore":
        void run("restore", async () => {
          if (!lastBackupPath) throw new HubAuthError(400, "NO_BACKUP_PATH");
          return hub.restoreBackup(lastBackupPath);
        });
        break;
      case "privacy_controls":
      case "privacy":
        void run("privacy", () =>
          hub.upsertPrivacy({
            youth_mode: true,
            data_minimization: true,
            export_allowed: false,
            retention_days: 180,
          }),
        );
        break;
      case "diagnostics":
        void run("diagnostics", () => hub.diagnostics());
        break;
      case "package_lifecycle":
        void run("package", () =>
          hub.recordPackageLifecycle({
            track_id: "DIGITAL_CONFIDENCE",
            package_version: "1.0.0",
            action: "install",
          }),
        );
        break;
      case "oneroster_import":
        void run("oneroster_status", () => hub.onerosterImportStatus());
        break;
      default:
        void run(w, async () => ({ note: `workflow ${w} acknowledged` }));
    }
  }

  return (
    <section aria-labelledby="admin-hardening-heading" data-testid="admin-hardening-panel">
      <h2 id="admin-hardening-heading">Admin / hardening</h2>
      <nav aria-label="Admin workflows">
        <ul>
          {workflows.map((w) => (
            <li key={w}>
              <button
                type="button"
                data-testid={`admin-workflow-${w}`}
                disabled={busy !== null}
                onClick={() => onWorkflow(w)}
              >
                {busy === w || (w === "backup_restore" && busy === "backup")
                  ? "Working…"
                  : w.replaceAll("_", " ")}
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              data-testid="admin-workflow-restore"
              disabled={busy !== null || !lastBackupPath}
              onClick={() => onWorkflow("restore")}
            >
              restore last backup
            </button>
          </li>
        </ul>
      </nav>
      {error ? (
        <div className="error-box" role="alert" data-testid="admin-hardening-error">
          {error}
        </div>
      ) : null}
      {result ? (
        <pre data-testid="admin-hardening-result" tabIndex={0}>
          {result}
        </pre>
      ) : null}
    </section>
  );
}
