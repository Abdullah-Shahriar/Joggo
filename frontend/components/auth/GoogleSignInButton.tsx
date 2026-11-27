"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import { apiRequest } from "@/lib/api";
import type { UserRole } from "@/lib/constants";
import type { AuthSessionResponse, AuthUser } from "@/lib/types";

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (cfg: {
            client_id: string;
            callback: (resp: { credential?: string }) => void;
          }) => void;
          renderButton: (
            el: HTMLElement,
            opts: { theme?: string; size?: string; width?: number; text?: string; locale?: string },
          ) => void;
        };
      };
    };
  }
}

type ConfigState = "loading" | "ready" | "unconfigured" | "error";

// Cache a fetched runtime Client ID in memory across /login <-> /signup route switches
let cachedRuntimeClientId = "";

const CONFIG_RETRY_DELAYS_MS = [2000, 4000, 6000, 8000];

export function GoogleSignInButton({
  portal = "doctor",
  mode = "signin",
  onSuccess,
  onError,
}: {
  portal?: UserRole;
  mode?: "signin" | "signup";
  onSuccess: (user: AuthUser) => void;
  onError: (message: string) => void;
}) {
  const buildTimeId = (process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "").trim();
  const initialId = buildTimeId || cachedRuntimeClientId;

  const [clientId, setClientId] = useState<string>(initialId);
  const [configState, setConfigState] = useState<ConfigState>(initialId ? "ready" : "loading");
  const [retryNonce, setRetryNonce] = useState<number>(0);
  const [scriptLoaded, setScriptLoaded] = useState<boolean>(false);
  const [scriptFailed, setScriptFailed] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  }, [onSuccess, onError]);

  // Fetch runtime Google Client ID from backend (/api/auth/config) with automatic retries
  // so a Render free-tier cold start or transient 502/504 never falsely disables Google sign-in.
  useEffect(() => {
    if (buildTimeId) {
      setClientId(buildTimeId);
      setConfigState("ready");
      return;
    }
    if (cachedRuntimeClientId) {
      setClientId(cachedRuntimeClientId);
      setConfigState("ready");
      return;
    }

    let active = true;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    setConfigState("loading");

    const fetchConfig = async (attempt: number) => {
      try {
        const res = await apiRequest<{ google_client_id: string | null }>("/auth/config", {
          redirectOn401: false,
          silentErrorToast: true,
        });
        if (!active) return;
        const resolved = (res.google_client_id || "").trim();
        if (resolved) {
          cachedRuntimeClientId = resolved;
          setClientId(resolved);
          setConfigState("ready");
        } else {
          setConfigState("unconfigured");
        }
      } catch {
        if (!active) return;
        if (attempt < CONFIG_RETRY_DELAYS_MS.length) {
          retryTimer = setTimeout(() => {
            if (active) void fetchConfig(attempt + 1);
          }, CONFIG_RETRY_DELAYS_MS[attempt]);
        } else {
          setConfigState("error");
        }
      }
    };

    void fetchConfig(0);

    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [buildTimeId, retryNonce]);

  // Detect Google GSI availability even when the script was already loaded on a prior route
  // or finishes asynchronously after clientId arrives from /api/auth/config.
  useEffect(() => {
    if (!clientId || scriptLoaded) return;
    if (typeof window !== "undefined" && window.google?.accounts?.id) {
      setScriptLoaded(true);
      return;
    }
    let checks = 0;
    const timer = window.setInterval(() => {
      checks += 1;
      if (window.google?.accounts?.id) {
        setScriptLoaded(true);
        window.clearInterval(timer);
      } else if (checks >= 40) {
        window.clearInterval(timer);
      }
    }, 150);
    return () => window.clearInterval(timer);
  }, [clientId, scriptLoaded]);

  useEffect(() => {
    if (!clientId || !scriptLoaded || !containerRef.current) return;
    const gsi = window.google?.accounts?.id;
    if (!gsi) return;

    const btnWidth = Math.max(240, Math.min(360, containerRef.current.offsetWidth || 340));

    gsi.initialize({
      client_id: clientId,
      callback: async (resp) => {
        if (!resp.credential) {
          onErrorRef.current("Google sign-in did not return a valid credential.");
          return;
        }
        try {
          const data = await apiRequest<AuthSessionResponse>("/auth/google", {
            method: "POST",
            body: { credential: resp.credential, portal },
            silentErrorToast: true,
          });
          onSuccessRef.current(data.user);
        } catch (err) {
          onErrorRef.current(err instanceof Error ? err.message : "Google sign-in failed.");
        }
      },
    });
    containerRef.current.innerHTML = "";
    gsi.renderButton(containerRef.current, {
      theme: "outline",
      size: "large",
      width: btnWidth,
      text: mode === "signup" ? "signup_with" : "continue_with",
      locale: "en",
    });
  }, [clientId, scriptLoaded, portal, mode]);

  if (configState === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex h-10 w-full animate-pulse items-center justify-center rounded border border-border bg-bg-subtle px-3 text-xs text-text-muted"
      >
        Loading Google sign-in…
      </div>
    );
  }

  if (configState === "error") {
    return (
      <button
        type="button"
        onClick={() => setRetryNonce((n) => n + 1)}
        className="flex h-10 w-full items-center justify-center rounded border border-border bg-bg px-3 text-sm font-medium text-text hover:bg-bg-subtle"
      >
        Server waking up — click to load Google sign-in
      </button>
    );
  }

  if (configState === "unconfigured" || !clientId) {
    return (
      <button
        type="button"
        disabled
        title="Set GOOGLE_CLIENT_ID on Render or NEXT_PUBLIC_GOOGLE_CLIENT_ID on Vercel to activate Gmail sign-in"
        className="flex h-10 w-full items-center justify-center rounded border border-border bg-bg-subtle px-3 text-sm text-text-muted"
      >
        {mode === "signup"
          ? "Sign up with Google (set GOOGLE_CLIENT_ID to activate)"
          : "Continue with Google (set GOOGLE_CLIENT_ID to activate)"}
      </button>
    );
  }

  if (scriptFailed) {
    return (
      <button
        type="button"
        disabled
        className="flex h-10 w-full items-center justify-center rounded border border-border bg-bg-subtle px-3 text-sm text-text-muted"
      >
        Google sign-in unavailable (blocked by browser or network)
      </button>
    );
  }

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client?hl=en"
        strategy="afterInteractive"
        onLoad={() => setScriptLoaded(true)}
        onReady={() => {
          if (typeof window !== "undefined" && window.google?.accounts?.id) {
            setScriptLoaded(true);
          }
        }}
        onError={() => setScriptFailed(true)}
      />
      <div ref={containerRef} className="flex min-h-[42px] w-full justify-center" />
    </>
  );
}
