export function portalReturnHref(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!/^https?:\/\//i.test(trimmed)) return null;
  return trimmed.replace(/\/+$/, "");
}
