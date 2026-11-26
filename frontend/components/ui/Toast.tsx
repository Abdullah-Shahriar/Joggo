"use client";

import { AlertCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

import { subscribeToasts, type ToastPayload } from "@/lib/api";

interface ToastEntry extends ToastPayload {
  id: number;
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  useEffect(() => {
    let counter = 1;
    return subscribeToasts((payload) => {
      const id = counter++;
      setToasts((prev) => [...prev.slice(-3), { ...payload, id }]);
      const ttl = payload.kind === "error" ? 6000 : 3000;
      setTimeout(() => {
        setToasts((prev) => prev.filter((item) => item.id !== id));
      }, ttl);
    });
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.kind === "error" ? "alert" : "status"}
          className="cs-toast-in flex items-start gap-2.5 rounded border border-border bg-bg px-3.5 py-2.5 text-sm text-text shadow-modal"
        >
          {toast.kind === "success" ? (
            <svg
              aria-hidden="true"
              className="mt-0.5 h-4 w-4 shrink-0 text-accent"
              viewBox="0 0 16 16"
              fill="none"
            >
              <path
                className="cs-check-draw"
                d="M3 8.5L6.5 12L13 4.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-text">{toast.message}</p>
            {toast.kind === "error" && toast.requestId && (
              <p className="mt-0.5 text-[11px] text-text-muted">Ref: {toast.requestId}</p>
            )}
          </div>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
            className="text-text-muted hover:text-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
