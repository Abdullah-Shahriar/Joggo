"use client";

import { LoaderHelix } from "@/components/ui/loader-helix";

export function BrandLoader({
  label = "Loading…",
  fullScreen = false,
}: {
  label?: string;
  fullScreen?: boolean;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        fullScreen
          ? "fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-bg px-4"
          : "flex flex-col items-center justify-center gap-4 py-12"
      }
    >
      <LoaderHelix dots={12} speed={1.5} />
      <p className="flex h-5 items-center text-sm font-medium text-text-muted">{label}</p>
    </div>
  );
}
