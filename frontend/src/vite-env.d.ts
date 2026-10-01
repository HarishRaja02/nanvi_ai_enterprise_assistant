/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "true" enables development sign-in (demo accounts). Must be "false" in production builds. */
  readonly VITE_DEMO_MODE?: string;
  /** Fully-qualified company SSO authorization URL, configured per deployment. */
  readonly VITE_SSO_LOGIN_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
