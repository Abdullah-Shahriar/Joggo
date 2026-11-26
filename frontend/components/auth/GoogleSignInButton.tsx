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
            opts: { theme?: string; size?: string; width?: number; text?: string },
          ) => void;
        };
      };
    };
  }
}

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
  const [clientId, setClientId] = useState<string>(buildTimeId);
  const [configChecked, setConfigChecked] = useState<boolean>(Boolean(buildTimeId));
  const [scriptLoaded, setScriptLoaded] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  }, [onSuccess, onError]);

  // Fetch runtime Google Client ID from backend (/api/auth/config) if not baked at build time
  useEffect(() => {
    if (buildTimeId) {
      setClientId(buildTimeId);
      setConfigChecked(true);
      return;
    }
    let active = true;
    apiRequest<{ google_client_id: string | null }>("/auth/config", {
      redirectOn401: false,
      silentErrorToast: true,
    })
      .then((res) => {
        if (!active) return;
        if (res.google_client_id) {
          setClientId(res.google_client_id);
        }
      })
      .catch(() => {
        // Ignore; button remains gracefully disabled
      })
      .finally(() => {
        if (active) setConfigChecked(true);
      });
    return () => {
      active = false;
    };
  }, [buildTimeId]);

  // Detect if Google GSI script was already loaded from a prior route navigation
  useEffect(() => {
    if (typeof window !== "undefined" && window.google?.accounts?.id) {
      setScriptLoaded(true);
    }
  }, [clientId]);

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
    });
  }, [clientId, scriptLoaded, portal, mode]);

  if (!configChecked) {
    return (
      <div className="h-10 w-full animate-pulse rounded border border-border bg-bg-subtle" />
    );
  }

  if (!clientId) {
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

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setScriptLoaded(true)}
      />
      <div ref={containerRef} className="flex min-h-[42px] w-full justify-center" />
    </>
  );
}
