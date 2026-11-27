"use client";

import { ArrowUpRight, Check, ClipboardCheck, ExternalLink, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ReviewConfirmCheckbox } from "@/components/documents/SignOutChecklist";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest, emitToast } from "@/lib/api";

type ExternalAiProvider = "gemini" | "chatgpt" | "claude";

const REDIRECT_DELAY_MS = 1500;
const MAX_URL_PROMPT_CHARS = 3400;

const AI_TARGETS: ReadonlyArray<{
  id: ExternalAiProvider;
  label: string;
  providerName: string;
  supportsUrlPrefill: boolean;
  iconSrc: string;
}> = [
  {
    id: "gemini",
    label: "Take to Gemini",
    providerName: "Gemini",
    supportsUrlPrefill: false,
    iconSrc: "/icons/gemini.png",
  },
  {
    id: "chatgpt",
    label: "Take to ChatGPT",
    providerName: "ChatGPT",
    supportsUrlPrefill: true,
    iconSrc: "/icons/chatgpt.png",
  },
  {
    id: "claude",
    label: "Take to Claude",
    providerName: "Claude",
    supportsUrlPrefill: true,
    iconSrc: "/icons/claude.png",
  },
];

function buildTargetUrl(provider: ExternalAiProvider, promptText: string): string {
  if (provider === "gemini") {
    return "https://gemini.google.com/app";
  }

  const truncated = promptText.length > MAX_URL_PROMPT_CHARS;
  const queryPayload = truncated
    ? `${promptText.slice(0, MAX_URL_PROMPT_CHARS)}\n\n[Truncated for URL length. Full text is copied to your clipboard; press Ctrl+V to paste everything.]`
    : promptText;
  const encoded = encodeURIComponent(queryPayload);

  if (provider === "chatgpt") {
    return `https://chatgpt.com/?q=${encoded}`;
  }
  return `https://claude.ai/new?q=${encoded}`;
}

async function copyTextReliable(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to textarea copy fallback
    }
  }
  if (typeof document !== "undefined") {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
  return false;
}

export function SendToAiButtons({
  documentId,
  sanitizedSha256,
  disabled = false,
}: {
  documentId: string;
  sanitizedSha256: string | null | undefined;
  disabled?: boolean;
}) {
  const [pendingTarget, setPendingTarget] = useState<(typeof AI_TARGETS)[number] | null>(null);
  const [approvedChecked, setApprovedChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [handoffState, setHandoffState] = useState<{
    provider: ExternalAiProvider;
    providerName: string;
    phase: "copied_waiting" | "opened" | "popup_blocked";
    url: string;
    copied: boolean;
    supportsUrlPrefill: boolean;
  } | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const isReady = Boolean(!disabled && sanitizedSha256);
  const isWaiting = handoffState?.phase === "copied_waiting";

  const openConfirmModal = (target: (typeof AI_TARGETS)[number]) => {
    if (!isReady || isWaiting) return;
    setPendingTarget(target);
    setApprovedChecked(false);
    setModalError(null);
  };

  const closeConfirmModal = () => {
    if (submitting) return;
    setPendingTarget(null);
    setApprovedChecked(false);
    setModalError(null);
  };

  const handleConfirmHandoff = async () => {
    if (!pendingTarget || !approvedChecked || !sanitizedSha256) return;

    const target = pendingTarget;
    setSubmitting(true);
    setModalError(null);

    try {
      const res = await apiRequest<{ prompt_text: string }>(
        `/documents/${documentId}/handoff`,
        {
          method: "POST",
          body: {
            provider: target.id,
            sanitized_sha256: sanitizedSha256,
          },
          silentErrorToast: true,
        },
      );

      setPendingTarget(null);
      setApprovedChecked(false);

      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      const url = buildTargetUrl(target.id, res.prompt_text);
      const copied = await copyTextReliable(res.prompt_text);

      setHandoffState({
        provider: target.id,
        providerName: target.providerName,
        phase: "copied_waiting",
        url,
        copied,
        supportsUrlPrefill: target.supportsUrlPrefill,
      });

      emitToast({
        kind: "success",
        message: copied
          ? `File copied in text format. Opening ${target.providerName} in 1.5 seconds.`
          : `Opening ${target.providerName} in 1.5 seconds.`,
      });

      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        const win = window.open(url, "_blank", "noopener,noreferrer");
        if (win) {
          setHandoffState((prev) => (prev ? { ...prev, phase: "opened" } : null));
        } else {
          setHandoffState((prev) => (prev ? { ...prev, phase: "popup_blocked" } : null));
          emitToast({
            kind: "error",
            message: `Pop-up was blocked by your browser. Select "Open ${target.providerName} now" below.`,
          });
        }
      }, REDIRECT_DELAY_MS);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not prepare external handoff. Please refresh and try again.";
      setModalError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      aria-label="Open privacy-safe text in an external AI chat"
      className="joggo-surface-sep mt-5 rounded border border-border bg-bg p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent-tint text-accent">
            <Sparkles className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-text">Continue in your preferred AI chat</h2>
            <p className="text-xs text-text-muted">
              Confirm your review to copy the cleaned text and open a new session on the AI website.
            </p>
          </div>
        </div>
        <span className="rounded border border-border bg-bg-subtle px-2 py-0.5 font-mono text-[11px] font-medium text-text-muted">
          TEXT · DE-IDENTIFIED
        </span>
      </div>

      {handoffState && (
        <div
          role="status"
          aria-live="polite"
          className={`mt-3.5 overflow-hidden rounded-md border px-3.5 py-2.5 text-sm ${
            handoffState.phase === "popup_blocked"
              ? "border-danger/40 bg-danger-tint text-danger"
              : "border-accent/40 bg-accent-tint/70 text-accent"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-medium">
              <ClipboardCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                {handoffState.phase === "copied_waiting"
                  ? handoffState.copied
                    ? `File copied in text format. Taking you to ${handoffState.providerName} in 1.5s.`
                    : `Taking you to ${handoffState.providerName} in 1.5s.`
                  : handoffState.phase === "opened"
                    ? handoffState.supportsUrlPrefill
                      ? `File copied and new ${handoffState.providerName} session opened.`
                      : `File copied and new ${handoffState.providerName} session opened. Press Ctrl+V inside the chat box.`
                    : "File copied in text format. Your browser paused the new tab."}
              </span>
            </div>

            {handoffState.phase !== "copied_waiting" && (
              <a
                href={handoffState.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded border border-current bg-bg px-2.5 py-1 text-xs font-semibold hover:opacity-90"
              >
                <span>Open {handoffState.providerName} now</span>
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            )}
          </div>

          {handoffState.phase === "copied_waiting" && (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-bg/80">
              <div
                className="h-full rounded-full bg-accent"
                style={{
                  animation: `joggo-handoff-fill ${REDIRECT_DELAY_MS}ms linear forwards`,
                }}
              />
            </div>
          )}
        </div>
      )}

      <div
        role="group"
        aria-label="Choose an AI assistant to open in a new session"
        className="mt-3.5 grid grid-cols-1 gap-2.5 sm:grid-cols-3"
      >
        {AI_TARGETS.map((item) => {
          const isThisWaiting =
            handoffState?.provider === item.id && handoffState.phase === "copied_waiting";
          const isThisOpened =
            handoffState?.provider === item.id && handoffState.phase === "opened";

          return (
            <button
              key={item.id}
              type="button"
              disabled={!isReady || isWaiting}
              aria-label={`${item.label} in a new web session`}
              onClick={() => openConfirmModal(item)}
              className={`joggo-btn-elevated group inline-flex h-11 w-full items-center justify-between gap-2.5 rounded-md border px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 ${
                isThisWaiting
                  ? "border-accent bg-accent-tint text-accent"
                  : "border-border bg-bg text-text hover:border-accent hover:bg-bg-subtle"
              }`}
            >
              <span className="flex min-w-0 items-center gap-2.5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.iconSrc}
                  alt=""
                  aria-hidden="true"
                  className="h-5 w-5 shrink-0 object-contain"
                />
                <span className="truncate">
                  {isThisWaiting ? "Copied. Opening…" : item.label}
                </span>
              </span>
              {isThisWaiting || isThisOpened ? (
                <Check className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
              ) : (
                <ArrowUpRight
                  className="h-4 w-4 shrink-0 text-text-muted transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent"
                  aria-hidden="true"
                />
              )}
            </button>
          );
        })}
      </div>

      <p className="mt-2.5 text-xs text-text-muted">
        {isReady
          ? "Drafts written outside JOGGO keep placeholders. Real details can only be restored for drafts generated here."
          : "Resolve all safety findings first to unlock external AI handoff. Drafts written outside JOGGO keep placeholders. Real details can only be restored for drafts generated here."}
      </p>

      <Modal
        open={Boolean(pendingTarget)}
        title={pendingTarget ? `Confirm ${pendingTarget.label}` : "Confirm handoff"}
        onClose={closeConfirmModal}
      >
        <p className="text-sm text-text-muted">
          Only the cleaned text with placeholders will be copied for{" "}
          <strong className="font-medium text-text">{pendingTarget?.providerName}</strong>. This
          action is recorded in the audit log.
        </p>

        <div className="mt-4">
          <ReviewConfirmCheckbox
            id="handoff-review-confirm"
            boxed
            checked={approvedChecked}
            onChange={setApprovedChecked}
            label="I reviewed the cleaned text and approve sending it"
          />
        </div>

        {modalError && (
          <div role="alert" className="mt-3 rounded bg-danger-tint px-3 py-2 text-xs text-danger">
            {modalError}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={closeConfirmModal} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={submitting}
            disabled={!approvedChecked}
            onClick={() => void handleConfirmHandoff()}
          >
            Continue to {pendingTarget?.providerName}
          </Button>
        </div>
      </Modal>
    </section>
  );
}
