/// <reference types="vite/client" />

interface ElectronAPI {
  isDesktop: boolean;
  platform: string;
  selectFolder: () => Promise<string | null>;
  showNotification: (title: string, body: string) => Promise<boolean>;
  openExternal: (url: string) => Promise<void>;
  onAccountBlocked: (callback: () => void) => void;
}

interface Window {
  electronAPI?: ElectronAPI;
}

interface ImportMetaEnv {
  /** "true" enables development sign-in (demo accounts). Must be "false" in production builds. */
  readonly VITE_DEMO_MODE?: string;
  /** Fully-qualified company SSO authorization URL, configured per deployment. */
  readonly VITE_SSO_LOGIN_URL?: string;
  /** Build target: "desktop" when bundled inside Electron, otherwise undefined/empty for web. */
  readonly VITE_APP_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
