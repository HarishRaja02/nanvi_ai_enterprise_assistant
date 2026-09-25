/**
 * Build-time configuration. Vite replaces `import.meta.env.*` with literals, so with
 * VITE_DEMO_MODE=false the demo-account code paths are eliminated from the bundle.
 */

/** Development sign-in via /dev/token. Never enable in production. */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

/**
 * Accept only an absolute https URL (or http on localhost for development). Anything else is
 * ignored rather than trusted, because this value becomes a full-page navigation target.
 */
export function parseSsoUrl(raw: string | undefined): string | null {
  const value = raw?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
    if (url.protocol === "https:" || (url.protocol === "http:" && local)) return url.toString();
  } catch {
    // Not a valid absolute URL.
  }
  return null;
}

export const SSO_LOGIN_URL = parseSsoUrl(import.meta.env.VITE_SSO_LOGIN_URL);

/**
 * Optional external hosted link / CDN URL for video animation.
 * Defaults to the local bundled public asset path `/assets/nanvi-ai-enterprise-animation.mp4`.
 */
export const HERO_VIDEO_URL =
  (import.meta.env.VITE_HERO_VIDEO_URL as string | undefined)?.trim() ||
  "/assets/nanvi-ai-enterprise-animation.mp4";

/**
 * Optional external hosted link / CDN URL for brand logos.
 * Defaults to local bundled public assets.
 */
export const LOGO_URL =
  (import.meta.env.VITE_LOGO_URL as string | undefined)?.trim() || "/nanvi-logo.png";

export const ICON_URL =
  (import.meta.env.VITE_ICON_URL as string | undefined)?.trim() || "/nanvi-n-icon.png";
