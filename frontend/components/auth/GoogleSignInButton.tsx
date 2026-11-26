"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import { apiRequest } from "@/lib/api";
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
  onSuccess,
  onError,
}: {
  onSuccess: (user: AuthUser) => void;
  onError: (message: string) => void;
}) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
  const containerRef = useRef<HTMLDivElement>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);

  useEffect(() => {
    if (!clientId || !scriptLoaded || !containerRef.current) return;
    const gsi = window.google?.accounts?.id;
    if (!gsi) return;

    gsi.initialize({
      client_id: clientId,
      callback: async (resp) => {
        if (!resp.credential) {
          onError("Google sign-in did not return a valid credential.");
          return;
        }
        try {
          const data = await apiRequest<AuthSessionResponse>("/auth/google", {
            method: "POST",
            body: { credential: resp.credential },
            silentErrorToast: true,
          });
          onSuccess(data.user);
        } catch (err) {
          onError(err instanceof Error ? err.message : "Google sign-in failed.");
        }
      },
    });
    containerRef.current.innerHTML = "";
    gsi.renderButton(containerRef.current, {
      theme: "outline",
      size: "large",
      width: 350,
      text: "continue_with",
    });
  }, [clientId, scriptLoaded, onSuccess, onError]);

  if (!clientId) {
    return (
      <button
        type="button"
        disabled
        className="flex h-10 w-full items-center justify-center rounded border border-border bg-bg-subtle text-sm text-text-muted"
      >
        Continue with Google (unavailable in local demo)
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
      <div ref={containerRef} className="flex min-h-[40px] w-full justify-center" />
    </>
  );
}
