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
          ? "flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4"
          : "flex flex-col items-center justify-center gap-4 py-12"
      }
    >
      <LoaderHelix variant="dna" dots={12} speed={1.8} />
      <p className="text-sm font-medium text-text-muted">{label}</p>
    </div>
  );
}
