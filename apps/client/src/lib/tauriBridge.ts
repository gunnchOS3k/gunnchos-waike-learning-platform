import { open } from "@tauri-apps/plugin-dialog";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function browseInstallPack(): Promise<string | null> {
  if (!isTauri()) return null;
  const selected = await open({
    directory: true,
    multiple: false,
    title: "Select verified learner pack directory",
  });
  if (!selected || Array.isArray(selected)) return null;
  return selected;
}
