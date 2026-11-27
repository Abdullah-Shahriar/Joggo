"use client";

import { useIsFetching } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { LoaderHelix } from "@/components/ui/loader-helix";
import { APP_NAME } from "@/lib/constants";

const INITIAL_LOAD_MS = 900;
const MIN_OVERLAY_MS = 750;
const FADE_OUT_MS = 180;
const MAX_OVERLAY_MS = 5000;

export function RouteProgressBar() {
  const pathname = usePathname();
  const fetching = useIsFetching();

  // Start visible=true so the DNA Helix splash animation appears immediately on first page load
  const [visible, setVisible] = useState(true);
  const [fading, setFading] = useState(false);

  const prevPathRef = useRef<string>(pathname);
  const shownAtRef = useRef<number>(0);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (fadeTimerRef.current) {
      clearTimeout(fadeTimerRef.current);
      fadeTimerRef.current = null;
    }
    if (safetyTimerRef.current) {
      clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  }, []);

  const scheduleHide = useCallback(
    (delayMs: number) => {
      clearTimers();
      hideTimerRef.current = setTimeout(() => {
        setFading(true);
        fadeTimerRef.current = setTimeout(() => {
          setVisible(false);
          setFading(false);
        }, FADE_OUT_MS);
      }, Math.max(0, delayMs));
    },
    [clearTimers],
  );

  const triggerOverlay = useCallback(() => {
    clearTimers();
    shownAtRef.current = Date.now();
    setFading(false);
    setVisible(true);

    // Safety fallback so overlay can never stick if a navigation is cancelled
    safetyTimerRef.current = setTimeout(() => {
      setFading(true);
      fadeTimerRef.current = setTimeout(() => {
        setVisible(false);
        setFading(false);
      }, FADE_OUT_MS);
    }, MAX_OVERLAY_MS);
  }, [clearTimers]);

  // 0. Play initial splash animation when the website first loads
  useEffect(() => {
    shownAtRef.current = Date.now();
    scheduleHide(INITIAL_LOAD_MS);
    return () => clearTimers();
  }, [scheduleHide, clearTimers]);

  // 1. Intercept clicks on any internal navigation link so the DNA animation appears immediately
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

      triggerOverlay();
    };

    document.addEventListener("click", handleDocumentClick, true);
    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
    };
  }, [pathname, triggerOverlay]);

  // 2. Also handle programmatic navigations (router.push / router.replace) & dismiss cleanly
  useEffect(() => {
    if (prevPathRef.current !== pathname) {
      prevPathRef.current = pathname;
      if (!visible) {
        shownAtRef.current = Date.now();
        setFading(false);
        setVisible(true);
        scheduleHide(MIN_OVERLAY_MS);
      } else {
        const elapsed = Date.now() - shownAtRef.current;
        scheduleHide(Math.max(0, MIN_OVERLAY_MS - elapsed));
      }
    }
  }, [pathname, visible, scheduleHide]);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  return (
    <>
      {fetching > 0 && !visible && (
        <div
          aria-hidden="true"
          className="fixed left-0 top-0 z-50 h-0.5 w-full overflow-hidden bg-accent-tint"
        >
          <div className="h-full w-2/3 bg-accent transition-all duration-150" />
        </div>
      )}

      {visible && (
        <div
          role="status"
          aria-live="polite"
          aria-label={`Loading ${APP_NAME}`}
          className={`fixed inset-0 z-[100] flex flex-col items-center justify-center gap-5 bg-bg/95 backdrop-blur-sm transition-opacity duration-150 ${
            fading ? "opacity-0" : "opacity-100"
          }`}
        >
          <LoaderHelix dots={12} speed={1.5} />
          <div className="flex items-center gap-2 text-sm font-medium text-text-muted">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt=""
              aria-hidden="true"
              className="h-5 w-auto object-contain"
            />
            <span>Loading {APP_NAME}…</span>
          </div>
        </div>
      )}
    </>
  );
}
