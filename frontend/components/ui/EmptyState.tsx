import Link from "next/link";

import { Button } from "./Button";

export function EmptyState({
  message,
  actionLabel,
  actionHref,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
}: {
  message: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
}) {
  const hasPrimary = Boolean(actionLabel && (actionHref || onAction));
  const hasSecondary = Boolean(secondaryActionLabel && onSecondaryAction);

  return (
    <div className="rounded border border-border bg-bg px-6 py-10 text-center">
      <p className="text-sm text-text-muted">{message}</p>
      {(hasPrimary || hasSecondary) && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          {actionLabel && actionHref ? (
            <Link
              href={actionHref}
              className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
            >
              {actionLabel}
            </Link>
          ) : actionLabel && onAction ? (
            <Button onClick={onAction}>{actionLabel}</Button>
          ) : null}
          {secondaryActionLabel && onSecondaryAction ? (
            <Button variant="ghost" onClick={onSecondaryAction}>
              {secondaryActionLabel}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
