"use client";

import { ArrowUpRight, Check, ClipboardCheck, ExternalLink, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { emitToast } from "@/lib/api";
import { formatTaskType } from "@/lib/format";
import type { TaskType } from "@/lib/types";

export type ExternalAiProvider = "gemini" | "chatgpt" | "claude";

const REDIRECT_DELAY_MS = 1500;
const MAX_URL_PROMPT_CHARS = 3400;

const TASK_HEADINGS_TEXT: Record<TaskType, string[]> = {
  discharge_summary: [
    "## Diagnosis",
    "## Clinical course",
    "## Key findings",
    "## Medications at discharge",
    "## Follow-up",
  ],
  case_summary: ["## Summary", "## Key findings", "## Concerns"],
  treatment_plan: ["## Assessment", "## Plan", "## Monitoring", "## Follow-up"],
};

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

function buildCleanHandoffPrompt(taskType: TaskType, sanitizedText: string): string {
  const headings = TASK_HEADINGS_TEXT[taskType].join("\n");
  return [
    `Write a structured ${formatTaskType(taskType).toLowerCase()} using only the privacy-safe clinical text below.`,
    "Copy all placeholders (such as [PATIENT_A], [DOCTOR_1], [DAY_0]) exactly as written and never guess or invent missing details.",
    "",
    "Required headings:",
    headings,
    "",
    "Clinical text (de-identified):",
    sanitizedText.trim(),
  ].join("\n");
}

function buildTargetUrl(provider: ExternalAiProvider, promptText: string): {
  url: string;
  truncatedInUrl: boolean;
} {
  if (provider === "gemini") {
    return { url: "https://gemini.google.com/app", truncatedInUrl: false };
  }

  const truncated = promptText.length > MAX_URL_PROMPT_CHARS;
  const queryPayload = truncated
    ? `${promptText.slice(0, MAX_URL_PROMPT_CHARS)}\n\n[Truncated for URL length — full text is copied to your clipboard; press Ctrl+V to paste everything.]`
    : promptText;
  const encoded = encodeURIComponent(queryPayload);

  if (provider === "chatgpt") {
    return { url: `https://chatgpt.com/?q=${encoded}`, truncatedInUrl: truncated };
  }
  return { url: `https://claude.ai/new?q=${encoded}`, truncatedInUrl: truncated };
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
  taskType,
  sanitizedText,
  disabled = false,
}: {
  taskType: TaskType;
  sanitizedText: string | null | undefined;
  disabled?: boolean;
}) {
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

  const isReady = Boolean(!disabled && sanitizedText && sanitizedText.trim().length > 0);
  const isWaiting = handoffState?.phase === "copied_waiting";

  const handleLaunch = async (target: (typeof AI_TARGETS)[number]) => {
    if (!isReady || !sanitizedText || isWaiting) return;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const fullPrompt = buildCleanHandoffPrompt(taskType, sanitizedText);
    const { url } = buildTargetUrl(target.id, fullPrompt);
    const copied = await copyTextReliable(fullPrompt);

    // 1. Clearly indicate to the user that the file text has been copied, and hold for 1.5s
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
        ? `File copied in text format! Opening ${target.providerName} in 1.5 seconds…`
        : `Preparing ${target.providerName} session…`,
    });

    // 2. After 1.5 seconds, navigate to the dedicated AI new session
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      const win = window.open(url, "_blank", "noopener,noreferrer");
      if (win) {
        setHandoffState((prev) =>
          prev ? { ...prev, phase: "opened" } : null,
        );
      } else {
        setHandoffState((prev) =>
          prev ? { ...prev, phase: "popup_blocked" } : null,
        );
        emitToast({
          kind: "error",
          message: `Pop-up was blocked by your browser — click "Open ${target.providerName} now" below.`,
        });
      }
    }, REDIRECT_DELAY_MS);
  };

  return (
    <section
      aria-label="Open privacy-safe text in an external AI chat"
      className="mt-5 rounded border border-[#D1D5DB] bg-bg p-4 shadow-[0_1px_3px_rgba(17,24,39,0.05)] sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent-tint text-accent">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-text">Continue in your preferred AI chat</h2>
            <p className="text-xs text-text-muted">
              Copies your cleaned file in text format, confirms for 1.5s, and opens a new session on the AI website.
            </p>
          </div>
        </div>
        <span className="rounded border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-text-muted">
          Text format · Privacy-safe
        </span>
      </div>

      {/* Clear 1.5-second copied confirmation & redirect banner */}
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
                    ? `File copied in text format! Taking you to ${handoffState.providerName} in 1.5s…`
                    : `Taking you to ${handoffState.providerName} in 1.5s…`
                  : handoffState.phase === "opened"
                    ? handoffState.supportsUrlPrefill
                      ? `File copied & new ${handoffState.providerName} session opened (full text is also on your clipboard).`
                      : `File copied & new ${handoffState.providerName} session opened — press Ctrl+V inside the chat box.`
                    : `File copied in text format! Your browser paused the new tab.`}
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
              onClick={() => void handleLaunch(item)}
              className={`group inline-flex h-11 w-full items-center justify-between gap-2.5 rounded-md border px-4 text-sm font-medium shadow-[0_1px_2px_rgba(17,24,39,0.04)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60 ${
                isThisWaiting
                  ? "border-accent bg-accent-tint text-accent"
                  : "border-[#D1D5DB] bg-bg text-text hover:border-accent hover:bg-bg-subtle"
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
                  {isThisWaiting ? "Copied! Opening…" : item.label}
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
          ? "Your privacy-safe text is always copied to your clipboard first. ChatGPT & Claude also pre-fill the chat box automatically; in Gemini just press Ctrl+V."
          : "Resolve all red safety conflicts first to unlock opening the privacy-safe text in Gemini, ChatGPT, or Claude."}
      </p>
    </section>
  );
}
