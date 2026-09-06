/**
 * Minimal Node declarations for the live-hub harness.
 *
 * The app itself never touches Node APIs, so pulling `@types/node` into the whole
 * project would widen the global scope for application code too. Declaring only
 * what this harness uses keeps `tsc --noEmit` strict everywhere else.
 */

declare module "node:child_process" {
  export interface ChildProcess {
    killed: boolean;
    stderr: { on(event: "data", cb: (chunk: { toString(): string }) => void): void } | null;
    on(event: "exit", cb: (code: number | null) => void): void;
    kill(signal?: string): boolean;
  }
  export function spawn(
    command: string,
    args: string[],
    options: { cwd?: string; stdio?: Array<"ignore" | "pipe" | "inherit"> },
  ): ChildProcess;
}

declare module "node:fs" {
  export function mkdtempSync(prefix: string): string;
  export function rmSync(path: string, options?: { recursive?: boolean; force?: boolean }): void;
}

declare module "node:os" {
  export function tmpdir(): string;
}

declare module "node:path" {
  export function join(...parts: string[]): string;
  export function resolve(...parts: string[]): string;
}

declare const __dirname: string;

declare const process: {
  env: Record<string, string | undefined>;
  stderr: { write(text: string): void };
};
