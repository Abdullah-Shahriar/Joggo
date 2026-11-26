"use client";

import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldWrapperProps {
  id: string;
  label: string;
  error?: string;
  helper?: string;
}

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & FieldWrapperProps
>(function Input({ id, label, error, helper, className = "", ...props }, ref) {
  const describedBy = error ? `${id}-error` : helper ? `${id}-helper` : undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-text">
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`joggo-input-sep h-10 w-full rounded border bg-bg px-3 text-base text-text placeholder:text-text-muted disabled:bg-bg-subtle disabled:text-text-muted ${
          error ? "border-danger" : "border-border"
        } ${className}`}
        {...props}
      />
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${id}-helper`} className="text-xs text-text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & FieldWrapperProps
>(function Select({ id, label, error, helper, className = "", children, ...props }, ref) {
  const describedBy = error ? `${id}-error` : helper ? `${id}-helper` : undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-text">
        {label}
      </label>
      <select
        ref={ref}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`joggo-input-sep h-10 w-full rounded border bg-bg px-3 text-base text-text disabled:bg-bg-subtle disabled:text-text-muted ${
          error ? "border-danger" : "border-border"
        } ${className}`}
        {...props}
      >
        {children}
      </select>
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${id}-helper`} className="text-xs text-text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & FieldWrapperProps
>(function Textarea({ id, label, error, helper, className = "", ...props }, ref) {
  const describedBy = error ? `${id}-error` : helper ? `${id}-helper` : undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-text">
        {label}
      </label>
      <textarea
        ref={ref}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`joggo-input-sep min-h-[112px] w-full rounded border bg-bg p-3 text-base text-text placeholder:text-text-muted disabled:bg-bg-subtle disabled:text-text-muted ${
          error ? "border-danger" : "border-border"
        } ${className}`}
        {...props}
      />
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : helper ? (
        <p id={`${id}-helper`} className="text-xs text-text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
});
