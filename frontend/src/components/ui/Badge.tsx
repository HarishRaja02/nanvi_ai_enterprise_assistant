import type { ReactNode } from "react";

type Tone = "neutral" | "primary" | "accent" | "success" | "warning" | "danger";

export function Badge({ tone = "neutral", className = "", children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return <span className={`badge${tone === "neutral" ? "" : ` badge-${tone}`}${className ? ` ${className}` : ""}`}>{children}</span>;
}
