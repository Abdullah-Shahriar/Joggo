import { formatComplaintStatus, formatDocStatus } from "@/lib/format";

export function DocumentStatusBadge({ status, pop = false }: { status: string; pop?: boolean }) {
  const isNeutral = status === "UPLOADED" || status === "PROCESSING" || status === "SENDING";
  const isDanger = status === "BLOCKED" || status === "FAILED" || status === "LLM_FAILED";

  const tone = isDanger
    ? "bg-danger-tint text-danger"
    : isNeutral
      ? "bg-bg-subtle text-text-muted"
      : "bg-accent-tint text-accent";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${tone} ${
        pop ? "cs-status-pop" : ""
      }`}
    >
      {isNeutral && (
        <svg
          aria-hidden="true"
          className="cs-spinner h-3 w-3"
          viewBox="0 0 16 16"
          fill="none"
        >
          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
          <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )}
      <span>{formatDocStatus(status)}</span>
    </span>
  );
}

export function SimpleStatusBadge({
  status,
  kind = "generic",
  pop = false,
}: {
  status: string;
  kind?: "user" | "complaint" | "outcome" | "generic";
  pop?: boolean;
}) {
  let label = status;
  let tone = "bg-bg-subtle text-text-muted";

  if (kind === "user") {
    label = status === "restricted" ? "Restricted" : "Active";
    tone = status === "restricted" ? "bg-danger-tint text-danger" : "bg-accent-tint text-accent";
  } else if (kind === "complaint") {
    label = formatComplaintStatus(status);
    tone =
      status === "resolved"
        ? "bg-accent-tint text-accent"
        : status === "in_progress"
          ? "bg-bg-subtle text-text"
          : "bg-bg-subtle text-text-muted";
  } else if (kind === "outcome") {
    label = status.charAt(0).toUpperCase() + status.slice(1);
    tone =
      status === "allowed"
        ? "bg-accent-tint text-accent"
        : status === "denied" || status === "error"
          ? "bg-danger-tint text-danger"
          : "bg-bg-subtle text-text-muted";
  }

  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${tone} ${
        pop ? "cs-status-pop" : ""
      }`}
    >
      {label}
    </span>
  );
}
