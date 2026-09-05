import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const PLATFORM_ROOT = resolve(__dirname, "../../../../..");
const PORT = Number(process.env.WAIKE_TEST_HUB_PORT || 8787);

let hub: ChildProcess | null = null;
let dbDir = "";

function python(): string {
  if (process.env.WAIKE_TEST_PYTHON) return process.env.WAIKE_TEST_PYTHON;
  return join(PLATFORM_ROOT, ".venv", "bin", "python");
}

async function waitForHealth(baseUrl: string, deadlineMs: number): Promise<void> {
  const stop = Date.now() + deadlineMs;
  let lastErr: unknown = null;
  while (Date.now() < stop) {
    try {
      const res = await fetch(`${baseUrl}/healthz`);
      if (res.ok) return;
      lastErr = new Error(`health ${res.status}`);
    } catch (err) {
      lastErr = err;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`hub did not become healthy: ${String(lastErr)}`);
}

export async function setup(): Promise<void> {
  dbDir = mkdtempSync(join(tmpdir(), "waike-live-hub-"));
  const baseUrl = `http://127.0.0.1:${PORT}`;
  hub = spawn(
    python(),
    [
      join(PLATFORM_ROOT, "scripts", "run_test_hub.py"),
      "--host",
      "127.0.0.1",
      "--port",
      String(PORT),
      "--db",
      join(dbDir, "live.sqlite3"),
    ],
    { cwd: PLATFORM_ROOT, stdio: ["ignore", "pipe", "pipe"] },
  );
  hub.stderr?.on("data", (chunk) => {
    const line = chunk.toString();
    if (line.includes("Traceback") || line.includes("Error")) process.stderr.write(line);
  });
  hub.on("exit", (code) => {
    if (code !== 0 && code !== null) process.stderr.write(`hub exited with ${code}\n`);
  });

  await waitForHealth(baseUrl, 45_000);
  process.env.WAIKE_LIVE_HUB_URL = baseUrl;
}

export async function teardown(): Promise<void> {
  if (hub && !hub.killed) {
    hub.kill("SIGTERM");
    await new Promise((r) => setTimeout(r, 500));
    if (!hub.killed) hub.kill("SIGKILL");
  }
  if (dbDir) rmSync(dbDir, { recursive: true, force: true });
}
