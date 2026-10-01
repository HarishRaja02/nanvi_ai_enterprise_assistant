import { useEffect, useState } from "react";

export const FONT_SCALE_STEPS = [0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5] as const;
export type FontScale = (typeof FONT_SCALE_STEPS)[number];

const STORAGE_KEY = "nanvi-font-scale";

function readSavedScale(): FontScale {
  try {
    const saved = Number(window.localStorage.getItem(STORAGE_KEY));
    return FONT_SCALE_STEPS.find((step) => Math.abs(step - saved) < 0.001) ?? 1;
  } catch {
    return 1;
  }
}

/** Keeps the reading-size preference for this browser and applies it app-wide. */
export function useFontScale() {
  const [fontScale, setFontScale] = useState<FontScale>(readSavedScale);

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontScale * 100}%`;
    try {
      window.localStorage.setItem(STORAGE_KEY, String(fontScale));
    } catch {
      // The preference still applies for this session when storage is unavailable.
    }
  }, [fontScale]);

  return { fontScale, setFontScale };
}
