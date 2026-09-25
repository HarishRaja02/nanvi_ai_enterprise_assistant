import type { CSSProperties } from "react";

/** Decorative placeholder. Callers announce loading via a role="status" wrapper. */
export function Skeleton({ width = "100%", height = 12, style }: { width?: string | number; height?: number; style?: CSSProperties }) {
  return <span className="skeleton" aria-hidden="true" style={{ width, height, ...style }} />;
}
