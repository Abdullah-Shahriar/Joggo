import { APP_NAME } from "@/lib/constants";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-semibold text-text">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.png"
        alt=""
        aria-hidden="true"
        className="h-7 w-auto shrink-0 object-contain"
      />
      {!compact && <span className="text-base tracking-tight">{APP_NAME}</span>}
    </span>
  );
}
