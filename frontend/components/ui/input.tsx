import { forwardRef } from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, id, className = "", ...props },
  ref,
) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  return (
    <div className="w-full">
      {label ? (
        <label htmlFor={inputId} className="mb-1.5 block text-xs font-medium text-slate-400">
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        className={`focus-ring h-9 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 text-sm text-slate-100 placeholder:text-ink-500 ${className}`}
        {...props}
      />
    </div>
  );
});

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, id, children, className = "", ...props },
  ref,
) {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  return (
    <div className="w-full">
      {label ? (
        <label htmlFor={selectId} className="mb-1.5 block text-xs font-medium text-slate-400">
          {label}
        </label>
      ) : null}
      <select
        ref={ref}
        id={selectId}
        className={`focus-ring h-9 w-full rounded-lg border border-ink-600 bg-ink-900 px-2.5 text-sm text-slate-100 ${className}`}
        {...props}
      >
        {children}
      </select>
    </div>
  );
});
