import { APP_NAME } from "@/lib/constants";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-semibold text-text">
      <svg
        aria-hidden="true"
        className="h-6 w-6 text-accent"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 3L4.5 6.2V11.8c0 4.8 3.2 8.2 7.5 9.2 4.3-1 7.5-4.4 7.5-9.2V6.2L12 3Z" />
        <path d="M12 8.5v7M8.5 12h7" />
      </svg>
      {!compact && <span className="text-base tracking-tight">{APP_NAME}</span>}
    </span>
  );
}
