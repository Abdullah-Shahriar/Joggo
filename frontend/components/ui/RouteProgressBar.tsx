"use client";

import { useIsFetching } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LoaderHelix } from "@/components/ui/loader-helix";
import { APP_NAME } from "@/lib/constants";

const MIN_OVERLAY_MS = 350;
const MAX_OVERLAY_MS = 5000;

export function RouteProgressBar() {
  const pathname = usePathname();
  const fetching = useIsFetching();
  const [routeOverlay, setRouteOverlay] = useState(false);
  const shownAtRef = useRef<number>(0);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = () => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (safetyTimerRef.current) {
      clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  };

  // Intercept clicks on internal navigation links so the DNA loader appears immediately
  useEffect(() => {
    const handleDocumentClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      const target = e.target as HTMLElement | null;
      const anchor = target?.closest("a");
      if (!anchor) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;

      const rawHref = anchor.getAttribute("href");
      if (
        !rawHref ||
        rawHref.startsWith("#") ||
        rawHref.startsWith("mailto:") ||
        rawHref.startsWith("tel:") ||
        rawHref.startsWith("javascript:")
      ) {
        return;
      }

      let dest: URL;
      try {
        dest = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (dest.origin !== window.location.origin) return;
      if (dest.pathname === pathname) return;

      clearTimers();
      shownAtRef.current = Date.now();
      setRouteOverlay(true);

      // Safety timeout so overlay can never stick if navigation is aborted
      safetyTimerRef.current = setTimeout(() => {
        setRouteOverlay(false);
      }, MAX_OVERLAY_MS);
    };

    document.addEventListener("click", handleDocumentClick, true);
    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
    };
  }, [pathname]);

  // Dismiss overlay smoothly once the destination route finishes rendering
  useEffect(() => {
    if (!routeOverlay) return;
    const elapsed = Date.now() - shownAtRef.current;
    const remaining = Math.max(0, MIN_OVERLAY_MS - elapsed);

    clearTimers();
    hideTimerRef.current = setTimeout(() => {
      setRouteOverlay(false);
    }, remaining);

    return () => {
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <>
      {fetching > 0 && !routeOverlay && (
        <div
          aria-hidden="true"
          className="fixed left-0 top-0 z-50 h-0.5 w-full overflow-hidden bg-accent-tint"
        >
          <div className="h-full w-2/3 bg-accent transition-all duration-150" />
        </div>
      )}

      {routeOverlay && (
        <div
          role="status"
          aria-live="polite"
          aria-label={`Loading ${APP_NAME}`}
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-4 bg-bg/95 backdrop-blur-sm"
        >
          <LoaderHelix variant="dna" dots={12} speed={1.6} />
          <div className="flex items-center gap-2 text-sm font-medium text-text-muted">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt=""
              aria-hidden="true"
              className="h-5 w-auto object-contain"
            />
            <span>Loading…</span>
          </div>
        </div>
      )}
    </>
  );
}
