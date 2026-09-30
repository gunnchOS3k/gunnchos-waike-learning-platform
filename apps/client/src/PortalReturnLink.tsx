import { portalReturnHref } from "./portalReturn";

export function PortalReturnLink() {
  const href = portalReturnHref(import.meta.env.VITE_GUNNCHOS_PORTAL_URL);
  if (!href) return null;
  return (
    <a className="portal-return" href={href} aria-label="Return to gunnchOS">
      ← gunnchOS
    </a>
  );
}
