import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";

type Tone = "info" | "success" | "warning" | "danger";
const ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, danger: CircleAlert } as const;

type AlertProps = {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  actions?: ReactNode;
  /** danger → role="alert" (assertive) so failures are announced; others are polite status. */
  className?: string;
};

export function Alert({ tone = "info", title, children, actions, className }: AlertProps) {
  const Icon = ICONS[tone];
  return (
    <div className={`alert alert-${tone}${className ? ` ${className}` : ""}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={18} aria-hidden="true" />
      <div className="alert-body">
        {title && <div className="alert-title">{title}</div>}
        {children && <p>{children}</p>}
        {actions && <div className="alert-actions">{actions}</div>}
      </div>
    </div>
  );
}
