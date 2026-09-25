import { ButtonHTMLAttributes, forwardRef } from "react";
import type { LucideIcon } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  /** Shows a spinner and blocks interaction while keeping the label for screen readers. */
  loading?: boolean;
  block?: boolean;
  icon?: LucideIcon;
};

const cx = (...parts: Array<string | false | undefined>) => parts.filter(Boolean).join(" ");

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, block, icon: Icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx("btn", `btn-${variant}`, size !== "md" && `btn-${size}`, block && "btn-block", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="spinner" aria-hidden="true" /> : Icon ? <Icon size={16} aria-hidden="true" /> : null}
      {children}
    </button>
  );
});

type IconButtonProps = Omit<ButtonProps, "children" | "icon"> & { icon: LucideIcon; label: string };

/** Icon-only control. `label` is mandatory so it always has an accessible name. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon: Icon, label, variant = "ghost", size = "md", className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={cx("btn", `btn-${variant}`, "btn-icon", size !== "md" && `btn-${size}`, className)}
      aria-label={label}
      title={label}
      {...rest}
    >
      <Icon size={size === "sm" ? 15 : 18} aria-hidden="true" />
    </button>
  );
});
