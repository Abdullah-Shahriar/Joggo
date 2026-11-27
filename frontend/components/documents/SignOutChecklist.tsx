"use client";

import { Check } from "lucide-react";

export function ReviewConfirmCheckbox({
  checked,
  disabled = false,
  onChange,
  label = "I reviewed the cleaned text",
  id,
  boxed = false,
  prominent = false,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label?: string;
  id?: string;
  boxed?: boolean;
  prominent?: boolean;
}) {
  const labelClass = prominent
    ? disabled
      ? "inline-flex cursor-not-allowed items-center gap-2.5 rounded border border-border bg-bg-subtle px-3 py-2 text-xs font-medium text-text-muted opacity-60"
      : checked
        ? "inline-flex cursor-pointer items-center gap-2.5 rounded border border-accent/50 bg-bg px-3 py-2 text-sm font-medium text-accent transition-colors"
        : "inline-flex cursor-pointer items-center gap-2.5 rounded border border-accent bg-accent-tint px-3 py-2 text-sm font-medium text-text shadow-[0_1px_2px_rgba(15,118,110,0.14)] transition-colors hover:bg-bg"
    : boxed
      ? `flex items-start gap-2.5 rounded border border-border bg-bg-subtle p-3 text-sm text-text ${
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        }`
      : `inline-flex items-center gap-2 text-xs font-medium text-text ${
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        }`;

  return (
    <label htmlFor={id} className={labelClass}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className={`${prominent ? "h-[18px] w-[18px]" : "h-4 w-4"} shrink-0 accent-accent`}
      />
      <span>{label}</span>
      {prominent && !disabled && !checked && (
        <span className="rounded border border-accent/40 bg-bg px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide text-accent">
          Required
        </span>
      )}
    </label>
  );
}

export function SignOutChecklist({
  identifiersReplaced,
  safetyPassed,
  reviewedChecked,
  canReview,
  onReviewedChange,
}: {
  identifiersReplaced: boolean;
  safetyPassed: boolean;
  reviewedChecked: boolean;
  canReview: boolean;
  onReviewedChange: (next: boolean) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Sign-out checklist"
      className="flex flex-col gap-1.5"
    >
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
        Sign-out checklist
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="inline-flex items-center gap-1.5 text-xs text-text">
          <span
            aria-hidden="true"
            className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] border ${
              identifiersReplaced
                ? "border-accent bg-accent-tint text-accent"
                : "border-border bg-bg-subtle text-text-muted"
            }`}
          >
            {identifiersReplaced && <Check className="h-3 w-3" strokeWidth={1.75} />}
          </span>
          <span className={identifiersReplaced ? "text-text" : "text-text-muted"}>
            Identifiers replaced
          </span>
        </span>

        <span className="inline-flex items-center gap-1.5 text-xs text-text">
          <span
            aria-hidden="true"
            className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] border ${
              safetyPassed
                ? "border-accent bg-accent-tint text-accent"
                : "border-border bg-bg-subtle text-text-muted"
            }`}
          >
            {safetyPassed && <Check className="h-3 w-3" strokeWidth={1.75} />}
          </span>
          <span className={safetyPassed ? "text-text" : "text-text-muted"}>
            Safety scan passed
          </span>
        </span>

        <ReviewConfirmCheckbox
          id="signout-review-confirm"
          prominent
          checked={reviewedChecked}
          disabled={!canReview}
          onChange={onReviewedChange}
          label="I reviewed the cleaned text"
        />
      </div>
    </div>
  );
}
