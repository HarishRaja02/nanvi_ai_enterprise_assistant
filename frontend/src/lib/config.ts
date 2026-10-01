export type AppMode = "development" | "demo" | "production";

const rawAppMode = (import.meta.env.VITE_APP_MODE as string | undefined)?.trim().toLowerCase();
export const APP_MODE: AppMode =
  rawAppMode === "production" || rawAppMode === "demo" || rawAppMode === "development"
    ? rawAppMode
    : import.meta.env.VITE_DEMO_MODE === "true"
    ? "demo"
    : import.meta.env.DEV
    ? "development"
    : "production";

export const IS_PRODUCTION = APP_MODE === "production";
export const ALLOWS_SYNTHETIC_DATA = APP_MODE !== "production";

/** Development sign-in via /dev/token or demo persona mocks. Never enabled in production. */
export const DEMO_MODE = !IS_PRODUCTION && (APP_MODE === "demo" || import.meta.env.VITE_DEMO_MODE === "true");

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

/**
 * Voice-First Enterprise Interface Feature Flag.
 * Governs activation of the dynamic workspace, streaming events, and voice-first interaction pipeline.
 * Can be overridden locally via localStorage.setItem("nanvi_voice_ui", "true"|"false").
 */
export const NANVI_VOICE_UI: boolean =
  typeof window !== "undefined" && window.localStorage?.getItem("nanvi_voice_ui") !== null
    ? window.localStorage.getItem("nanvi_voice_ui") === "true"
    : import.meta.env.VITE_NANVI_VOICE_UI !== "false";
