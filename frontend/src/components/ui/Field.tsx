import { InputHTMLAttributes, ReactNode, forwardRef, useId } from "react";
import { CircleAlert } from "lucide-react";

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
  /** Extra control rendered inside the input (e.g. show/hide password). */
  adornment?: ReactNode;
};

/** Label + control + hint + inline error, wired together for assistive tech. */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, adornment, required, id, ...rest },
  ref,
) {
  const auto = useId();
  const inputId = id ?? auto;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [hint ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label className="field-label" htmlFor={inputId}>
        {label}
        {required && <span className="req" aria-hidden="true"> *</span>}
      </label>
      <div className={adornment ? "input-group" : undefined}>
        <input
          ref={ref}
          id={inputId}
          className="input"
          required={required}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...rest}
        />
        {adornment}
      </div>
      {hint && !error && <span id={hintId} className="field-hint">{hint}</span>}
      {error && (
        <span id={errorId} className="field-error">
          <CircleAlert size={13} aria-hidden="true" />
          {error}
        </span>
      )}
    </div>
  );
});
