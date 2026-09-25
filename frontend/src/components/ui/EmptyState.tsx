import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export function EmptyState({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state-icon"><Icon size={20} aria-hidden="true" /></div>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
