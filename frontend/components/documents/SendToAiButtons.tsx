"use client";

import { ArrowUpRight, Check, Sparkles } from "lucide-react";
import { useState } from "react";

import { emitToast } from "@/lib/api";
import { formatTaskType } from "@/lib/format";
import type { TaskType } from "@/lib/types";

export type ExternalAiProvider = "gemini" | "chatgpt" | "claude";

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
}> = [
  { id: "gemini", label: "Take to Gemini", providerName: "Gemini", supportsUrlPrefill: false },
  { id: "chatgpt", label: "Take to ChatGPT", providerName: "ChatGPT", supportsUrlPrefill: true },
  { id: "claude", label: "Take to Claude", providerName: "Claude", supportsUrlPrefill: true },
];

const MAX_URL_PROMPT_CHARS = 3400;

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

export function SendToAiButtons({
  taskType,
  sanitizedText,
  disabled = false,
}: {
  taskType: TaskType;
  sanitizedText: string | null | undefined;
  disabled?: boolean;
}) {
  const [recentTarget, setRecentTarget] = useState<ExternalAiProvider | null>(null);
  const isReady = Boolean(!disabled && sanitizedText && sanitizedText.trim().length > 0);

  const handleLaunch = (target: (typeof AI_TARGETS)[number]) => {
    if (!isReady || !sanitizedText) return;

    const fullPrompt = buildCleanHandoffPrompt(taskType, sanitizedText);
    const { url, truncatedInUrl } = buildTargetUrl(target.id, fullPrompt);

    // Open synchronously inside the click gesture so browser popup blockers allow the new session tab
    const win = window.open(url, "_blank", "noopener,noreferrer");

    // Always copy full text to clipboard in parallel (essential for Gemini & long documents)
    const copyPromise =
      typeof navigator !== "undefined" && navigator.clipboard?.writeText
        ? navigator.clipboard.writeText(fullPrompt).then(
            () => true,
            () => false,
          )
        : Promise.resolve(false);

    setRecentTarget(target.id);
    setTimeout(() => {
      setRecentTarget((prev) => (prev === target.id ? null : prev));
    }, 2500);

    void copyPromise.then((copied) => {
      if (!win) {
        emitToast({
          kind: "error",
          message: copied
            ? `Pop-up blocked for ${target.providerName}. Allow pop-ups and try again — full text is already copied.`
            : `Pop-up blocked for ${target.providerName}. Please allow pop-ups for this site.`,
        });
        return;
      }

      if (!target.supportsUrlPrefill) {
        emitToast({
          kind: "success",
          message: copied
            ? `Opened a new ${target.providerName} session and copied your privacy-safe text — press Ctrl+V to paste.`
            : `Opened a new ${target.providerName} session.`,
        });
      } else if (truncatedInUrl) {
        emitToast({
          kind: "success",
          message: copied
            ? `Opened ${target.providerName} with a preview and copied the full text — press Ctrl+V to paste all of it.`
            : `Opened a new ${target.providerName} session with your privacy-safe text.`,
        });
      } else {
        emitToast({
          kind: "success",
          message: `Opened a new ${target.providerName} session with your privacy-safe text ready in the chat box.`,
        });
      }
    });
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
              Opens a new web session with the cleaned, privacy-safe text format (no extensions or API keys needed).
            </p>
          </div>
        </div>
        <span className="rounded border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-text-muted">
          Text format · Privacy-safe
        </span>
      </div>

      <div
        role="group"
        aria-label="Choose an AI assistant to open in a new session"
        className="mt-3.5 grid grid-cols-1 gap-2.5 sm:grid-cols-3"
      >
        {AI_TARGETS.map((item) => {
          const isRecent = recentTarget === item.id;
          return (
            <button
              key={item.id}
              type="button"
              disabled={!isReady}
              aria-label={`${item.label} in a new web session`}
              onClick={() => handleLaunch(item)}
              className="group inline-flex h-11 w-full items-center justify-between gap-2 rounded-md border border-[#D1D5DB] bg-bg px-4 text-sm font-medium text-text shadow-[0_1px_2px_rgba(17,24,39,0.04)] transition-all hover:border-accent hover:bg-bg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="truncate">{item.label}</span>
              {isRecent ? (
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
          ? "ChatGPT and Claude pre-fill your cleaned text directly in the new chat box. Gemini opens a new chat with your full text copied to the clipboard (press Ctrl+V)."
          : "Resolve all red safety conflicts first to unlock opening the privacy-safe text in Gemini, ChatGPT, or Claude."}
      </p>
    </section>
  );
}
