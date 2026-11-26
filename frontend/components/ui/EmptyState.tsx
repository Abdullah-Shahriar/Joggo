import Link from "next/link";

import { Button } from "./Button";

export function EmptyState({
  message,
  actionLabel,
  actionHref,
  onAction,
}: {
  message: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded border border-border bg-bg px-6 py-10 text-center">
      <p className="text-sm text-text-muted">{message}</p>
      {actionLabel && actionHref ? (
        <div className="mt-4">
          <Link
            href={actionHref}
            className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
          >
            {actionLabel}
          </Link>
        </div>
      ) : actionLabel && onAction ? (
        <div className="mt-4">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      ) : null}
    </div>
  );
}
