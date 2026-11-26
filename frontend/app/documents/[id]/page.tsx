"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownCircle,
  Check,
  Copy,
  Download,
  FileText,
  HelpCircle,
  Trash2,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Modal";
import { PaneSkeleton } from "@/components/ui/Skeleton";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { apiBlob, apiRequest, emitToast } from "@/lib/api";
import type {
  DocumentDetail,
  DocumentResultResponse,
  OriginalTextResponse,
  SafetyFindingView,
  SanitizedTextResponse,
} from "@/lib/types";

const MARK_TYPES = [
  { value: "PATIENT", label: "Name" },
  { value: "DOCTOR", label: "Doctor" },
  { value: "PERSON", label: "Person" },
  { value: "PHONE", label: "Phone" },
  { value: "EMAIL", label: "Email" },
  { value: "ID", label: "ID" },
  { value: "MRN", label: "Record number" },
  { value: "LOCATION", label: "Address" },
  { value: "FACILITY", label: "Clinic / Hospital" },
  { value: "OTHER", label: "Other" },
] as const;

const TRACKER_STAGES = [
  { key: "extract", label: "Read file" },
  { key: "detect", label: "Find private info" },
  { key: "tokenize", label: "Hide details" },
  { key: "safety", label: "Safety check" },
  { key: "review", label: "Doctor review" },
  { key: "generate", label: "Write draft" },
];

const TOKEN_SPLIT_RE =
  /(\[(?:PATIENT|DOCTOR|PERSON|PHONE|EMAIL|ID|MRN|LOCATION|FACILITY|URL|IP|OTHER|DAY)_[A-Z0-9?-]+\]|\bAge\s+(?:\d{1,2}|90\+)|\b90\+\s+years)/g;

function renderTokensInLine(lineText: string) {
  const segments = lineText.split(TOKEN_SPLIT_RE);
  return segments.map((seg, idx) => {
    const isToken = TOKEN_SPLIT_RE.test(seg);
    TOKEN_SPLIT_RE.lastIndex = 0;
    if (isToken) {
      return (
        <span
          key={idx}
          className="inline-block rounded bg-accent-tint px-1.5 py-0.5 text-[13px] font-semibold text-accent"
        >
          {seg}
        </span>
      );
    }
    return <Fragment key={idx}>{seg}</Fragment>;
  });
}

function isHeadingLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.length > 70) return false;
  if (/^#{1,4}\s+/.test(trimmed)) return true;
  if (/^[A-Z][A-Z0-9\s/&()-]{3,}$/.test(trimmed) && !trimmed.includes(":")) return true;
  return false;
}

function renderFormattedOriginal(
  text: string,
  highlights: OriginalTextResponse["highlights"],
) {
  if (!highlights.length) {
    return text.split("\n").map((line, i) => {
      const trimmed = line.trim();
      if (!trimmed) return <div key={i} className="h-3" />;
      if (isHeadingLine(trimmed)) {
        return (
          <h3
            key={i}
            className="mt-4 mb-1.5 border-b border-border pb-1 text-sm font-semibold uppercase tracking-wide text-text first:mt-0"
          >
            {trimmed.replace(/^#{1,4}\s+/, "")}
          </h3>
        );
      }
      return (
        <p key={i} className="mb-1.5 leading-relaxed text-text">
          {line}
        </p>
      );
    });
  }

  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const parts: Array<{ key: string; content: string; highlighted: boolean; token?: string }> = [];
  let cursor = 0;

  for (const h of sorted) {
    if (h.start < cursor || h.start >= text.length) continue;
    const end = Math.min(h.end, text.length);
    if (h.start > cursor) {
      parts.push({ key: `t-${cursor}`, content: text.slice(cursor, h.start), highlighted: false });
    }
    parts.push({
      key: `h-${h.start}-${end}`,
      content: text.slice(h.start, end),
      highlighted: true,
      token: h.token,
    });
    cursor = end;
  }
  if (cursor < text.length) {
    parts.push({ key: `t-${cursor}`, content: text.slice(cursor), highlighted: false });
  }

  return (
    <div className="whitespace-pre-wrap break-words leading-7 text-text">
      {parts.map((p) =>
        p.highlighted ? (
          <mark
            key={p.key}
            title={`Hidden as ${p.token}`}
            className="rounded bg-accent-tint px-1 py-0.5 font-medium text-text"
          >
            {p.content}
          </mark>
        ) : (
          <Fragment key={p.key}>{p.content}</Fragment>
        ),
      )}
    </div>
  );
}

function renderModifiedPdfLines(
  text: string,
  findings: SafetyFindingView[],
  activeJumpIdx: number | null,
) {
  const rawLines = text.split("\n");
  let cursor = 0;

  return rawLines.map((line, lineIdx) => {
    const lineStart = cursor;
    const lineEnd = lineStart + line.length;
    cursor = lineEnd + 1;

    const matchingFindings = findings
      .map((f, fIdx) => ({ f, fIdx }))
      .filter(({ f }) => f.start <= lineEnd && f.end >= lineStart);
    const hasIssue = matchingFindings.length > 0;
    const isActiveJump =
      activeJumpIdx !== null && matchingFindings.some(({ fIdx }) => fIdx === activeJumpIdx);
    const primaryFindingIdx = hasIssue ? matchingFindings[0].fIdx : null;
    const trimmed = line.trim();

    if (hasIssue) {
      return (
        <div
          key={lineIdx}
          id={primaryFindingIdx !== null ? `safety-issue-${primaryFindingIdx}` : undefined}
          className={`my-1.5 rounded-r border-l-4 border-danger bg-danger-tint px-3 py-2 text-danger ${
            isActiveJump ? "ring-2 ring-danger ring-offset-1" : ""
          }`}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium text-danger">{renderTokensInLine(line || " ")}</span>
            <span className="shrink-0 rounded bg-bg px-1.5 py-0.5 text-[11px] font-semibold text-danger">
              Needs review: {matchingFindings[0].f.type}
            </span>
          </div>
        </div>
      );
    }

    if (!trimmed) {
      return <div key={lineIdx} className="h-3" />;
    }

    if (isHeadingLine(trimmed)) {
      return (
        <div
          key={lineIdx}
          className="mt-4 mb-1.5 border-b border-border pb-1 text-sm font-semibold uppercase tracking-wide text-text first:mt-0"
        >
          {renderTokensInLine(line)}
        </div>
      );
    }

    const kvMatch = line.match(/^([A-Za-z][A-Za-z0-9\s/()-]{1,32}:)(\s+.*)$/);
    if (kvMatch) {
      return (
        <div key={lineIdx} className="mb-1.5 leading-7 text-text">
          <span className="font-semibold text-text">{kvMatch[1]}</span>
          <span>{renderTokensInLine(kvMatch[2])}</span>
        </div>
      );
    }

    return (
      <div key={lineIdx} className="mb-1.5 leading-7 text-text">
        {renderTokensInLine(line)}
      </div>
    );
  });
}

function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-text">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={idx}>{part}</Fragment>;
  });
}

function renderCleanDraftPdf(text: string) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = (keyPrefix: string) => {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={`${keyPrefix}-ul`} className="my-2 list-disc space-y-1.5 pl-5 text-[15px] leading-relaxed text-text">
        {listItems.map((item, i) => (
          <li key={i}>{renderInlineBold(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  lines.forEach((rawLine, idx) => {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      flushList(`empty-${idx}`);
      return;
    }

    const bulletMatch = trimmed.match(/^[-*•]\s+(.*)$/);
    if (bulletMatch) {
      listItems.push(bulletMatch[1]);
      return;
    }

    flushList(`line-${idx}`);

    const headingMatch = trimmed.match(/^#{1,4}\s+(.*)$/);
    if (headingMatch) {
      blocks.push(
        <h3
          key={`h-${idx}`}
          className="mt-5 mb-2 border-b border-border pb-1 text-base font-semibold text-text first:mt-0"
        >
          {renderInlineBold(headingMatch[1])}
        </h3>,
      );
      return;
    }

    if (/^[-_]{3,}$/.test(trimmed)) {
      blocks.push(<hr key={`hr-${idx}`} className="my-4 border-border" />);
      return;
    }

    blocks.push(
      <p key={`p-${idx}`} className="mb-2.5 text-[15px] leading-relaxed text-text">
        {renderInlineBold(trimmed)}
      </p>,
    );
  });

  flushList("end");
  return blocks;
}

function DocumentReviewContent() {
  const params = useParams<{ id: string }>();
  const docId = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [mobileTab, setMobileTab] = useState<"cleaned" | "original" | "result">("cleaned");
  const [originalTab, setOriginalTab] = useState<"text" | "file">("text");
  const [showWhy, setShowWhy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [filePreview, setFilePreview] = useState<{ url: string; mime: string } | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [activeFindingIdx, setActiveFindingIdx] = useState<number | null>(null);

  const resultSectionRef = useRef<HTMLElement>(null);
  const cleanedRef = useRef<HTMLDivElement>(null);
  const [selectedText, setSelectedText] = useState<string>("");
  const [markType, setMarkType] = useState<string>("PATIENT");

  const { data: doc, isLoading, isError, refetch } = useQuery<DocumentDetail>({
    queryKey: ["document", docId],
    queryFn: () => apiRequest<DocumentDetail>(`/documents/${docId}`),
    refetchInterval: (query) => {
      const st = query.state.data?.status;
      if (!st || st === "UPLOADED" || st === "PROCESSING" || st === "SENDING") {
        return 1500;
      }
      return false;
    },
  });

  const canLoadText = Boolean(doc && !["UPLOADED", "PROCESSING"].includes(doc.status));

  const { data: originalData, isLoading: origLoading } = useQuery<OriginalTextResponse | null>({
    queryKey: ["document", docId, "original-text", doc?.version],
    queryFn: async () => {
      try {
        return await apiRequest<OriginalTextResponse>(`/documents/${docId}/original-text`, {
          silentErrorToast: true,
        });
      } catch {
        return null;
      }
    },
    enabled: canLoadText && !doc?.vault_expired,
  });

  const { data: sanitizedData, isLoading: sanLoading } = useQuery<SanitizedTextResponse | null>({
    queryKey: ["document", docId, "sanitized", doc?.version],
    queryFn: async () => {
      try {
        return await apiRequest<SanitizedTextResponse>(`/documents/${docId}/sanitized`, {
          silentErrorToast: true,
        });
      } catch {
        return null;
      }
    },
    enabled: canLoadText && doc?.status !== "FAILED",
  });

  const { data: resultData } = useQuery<DocumentResultResponse>({
    queryKey: ["document", docId, "result", doc?.status],
    queryFn: () => apiRequest<DocumentResultResponse>(`/documents/${docId}/result`),
    enabled: doc?.status === "COMPLETED",
  });

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    if (originalTab !== "file" || !doc || doc.vault_expired) {
      return;
    }
    setFileLoading(true);
    apiBlob(`/documents/${docId}/original-pdf`, { silentErrorToast: true })
      .then(({ blob }) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setFilePreview({ url: objectUrl, mime: blob.type || "application/pdf" });
      })
      .catch(() => {
        if (active) setFilePreview(null);
      })
      .finally(() => {
        if (active) setFileLoading(false);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [originalTab, docId, doc?.vault_expired, doc]);

  const markMutation = useMutation({
    mutationFn: async () => {
      if (!doc || !selectedText) return;
      return apiRequest(`/documents/${docId}/manual-marks`, {
        method: "POST",
        headers: { "If-Match": String(doc.version) },
        body: { text: selectedText, entity_type: markType },
      });
    },
    onSuccess: () => {
      setSelectedText("");
      setActiveFindingIdx(null);
      emitToast({ kind: "success", message: "Hidden everywhere in the document." });
      queryClient.invalidateQueries({ queryKey: ["document", docId] });
    },
  });

  const approveAndSendMutation = useMutation({
    mutationFn: async () => {
      if (!doc || !sanitizedData) return;
      if (doc.status === "REVIEW_REQUIRED") {
        await apiRequest(`/documents/${docId}/approve`, {
          method: "POST",
          body: { sanitized_sha256: sanitizedData.sanitized_sha256 },
        });
      }
      const idemKey =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random()}`;
      await apiRequest(`/documents/${docId}/send`, {
        method: "POST",
        headers: { "Idempotency-Key": idemKey },
      });
    },
    onSuccess: () => {
      setMobileTab("result");
      queryClient.invalidateQueries({ queryKey: ["document", docId] });
      setTimeout(() => {
        resultSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => apiRequest(`/documents/${docId}/retry`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", docId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiRequest(`/documents/${docId}`, { method: "DELETE" }),
    onSuccess: () => {
      setConfirmDelete(false);
      queryClient.removeQueries({ queryKey: ["document", docId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      emitToast({ kind: "success", message: "Document deleted." });
      router.replace("/documents");
    },
    onError: () => {
      setConfirmDelete(false);
    },
  });

  const jumpToIssue = (idx: number) => {
    setMobileTab("cleaned");
    setActiveFindingIdx(idx);
    setTimeout(() => {
      const target = document.getElementById(`safety-issue-${idx}`);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
  };

  const handleCycleJump = () => {
    const findings = sanitizedData?.findings || [];
    if (findings.length === 0) return;
    const nextIdx = activeFindingIdx === null ? 0 : (activeFindingIdx + 1) % findings.length;
    jumpToIssue(nextIdx);
  };

  const handleCleanedMouseUp = () => {
    if (!doc || doc.vault_expired || !["BLOCKED", "REVIEW_REQUIRED", "APPROVED"].includes(doc.status)) {
      return;
    }
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      setSelectedText("");
      return;
    }
    const text = sel.toString().trim();
    if (text.length >= 2 && text.length <= 200) {
      setSelectedText(text);
    } else {
      setSelectedText("");
    }
  };

  const handleExport = async (fmt: "txt" | "docx") => {
    const { blob, filename } = await apiBlob(`/documents/${docId}/export?format=${fmt}`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `summary.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!resultData?.text) return;
    await navigator.clipboard.writeText(resultData.text);
    emitToast({ kind: "success", message: "Copied to clipboard." });
  };

  const { currentStageIdx, stageError } = useMemo(() => {
    if (!doc) return { currentStageIdx: 0, stageError: false };
    if (doc.status === "COMPLETED") return { currentStageIdx: 6, stageError: false };
    if (doc.status === "SENDING") return { currentStageIdx: 5, stageError: false };
    if (doc.status === "LLM_FAILED") return { currentStageIdx: 5, stageError: true };
    if (doc.status === "APPROVED") return { currentStageIdx: 5, stageError: false };
    if (doc.status === "REVIEW_REQUIRED") return { currentStageIdx: 4, stageError: false };
    if (doc.status === "BLOCKED") return { currentStageIdx: 3, stageError: true };
    if (doc.status === "FAILED") return { currentStageIdx: 1, stageError: true };
    return { currentStageIdx: 1, stageError: false };
  }, [doc]);

  if (isLoading) {
    return <BrandLoader label="Loading document…" />;
  }

  if (isError || !doc) {
    return (
      <div className="rounded bg-danger-tint p-4 text-sm text-danger">
        Could not load this document.{" "}
        <button type="button" onClick={() => refetch()} className="font-medium underline">
          Try again
        </button>
      </div>
    );
  }

  const findings = sanitizedData?.findings || [];
  const hasSafetyIssues = findings.length > 0;
  const safetyPass = doc.safety_report?.status === "PASS";
  const vaultExpiredBeforeApproval =
    doc.vault_expired && ["BLOCKED", "REVIEW_REQUIRED", "APPROVED", "FAILED"].includes(doc.status);
  const canApproveAndSend =
    safetyPass &&
    !vaultExpiredBeforeApproval &&
    (doc.status === "REVIEW_REQUIRED" || doc.status === "APPROVED") &&
    Boolean(sanitizedData?.sanitized_sha256);

  const currentStageLabel =
    currentStageIdx < TRACKER_STAGES.length ? TRACKER_STAGES[currentStageIdx].label : "Complete";
  const nextStageLabel =
    currentStageIdx + 1 < TRACKER_STAGES.length ? TRACKER_STAGES[currentStageIdx + 1].label : null;

  return (
    <div>
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-text">{doc.original_filename}</h1>
          <DocumentStatusBadge status={doc.status} />
        </div>
        <Button variant="secondary" size="sm" onClick={() => setShowWhy((v) => !v)}>
          <HelpCircle className="h-4 w-4" aria-hidden="true" />
          Why was this hidden?
        </Button>
      </div>

      {/* High-visibility Step Progression Indicator */}
      <section
        aria-label="Document processing progress"
        className="mt-5 rounded border border-border bg-bg-subtle p-4"
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="font-semibold text-text">
            Current step:{" "}
            <span className={stageError ? "text-danger" : "text-accent"}>{currentStageLabel}</span>
          </span>
          {nextStageLabel && (
            <span className="text-text-muted">
              Next step: <strong className="font-medium text-text">{nextStageLabel}</strong>
            </span>
          )}
        </div>

        <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {TRACKER_STAGES.map((stage, idx) => {
            const done = idx < currentStageIdx;
            const current = idx === currentStageIdx;
            const next = idx === currentStageIdx + 1;
            const errored = current && stageError;

            return (
              <li
                key={stage.key}
                aria-current={current ? "step" : undefined}
                className={`flex items-center gap-2.5 rounded border px-3 py-2 text-xs ${
                  errored
                    ? "border-danger bg-danger-tint text-danger"
                    : current
                      ? "border-accent bg-bg font-semibold text-accent shadow-sm"
                      : done
                        ? "border-accent/30 bg-accent-tint/70 text-accent"
                        : next
                          ? "border-[#D1D5DB] bg-bg text-text"
                          : "border-border bg-bg text-text-muted"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                    errored
                      ? "bg-danger text-white"
                      : done
                        ? "bg-accent text-white"
                        : current
                          ? "bg-accent text-white"
                          : "bg-bg-subtle text-text-muted"
                  }`}
                >
                  {done ? <Check className="h-3.5 w-3.5" /> : idx + 1}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{stage.label}</p>
                  {current && (
                    <p className="text-[10px] uppercase tracking-wide">
                      {errored ? "Action needed" : "Active"}
                    </p>
                  )}
                  {next && !errored && (
                    <p className="text-[10px] uppercase tracking-wide text-text-muted">Next</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      {/* Banners */}
      {vaultExpiredBeforeApproval && (
        <div role="alert" className="mt-4 rounded border border-danger bg-danger-tint px-4 py-3 text-[15px] text-danger">
          Temporary private memory expired. Please upload the file again.
        </div>
      )}

      {doc.status === "FAILED" && (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded border border-danger bg-danger-tint px-4 py-3 text-[15px] text-danger"
        >
          <span>Could not process this file ({doc.failure_code || "ERROR"}).</span>
          {!doc.vault_expired && (
            <Button
              variant="secondary"
              size="sm"
              loading={retryMutation.isPending}
              onClick={() => retryMutation.mutate()}
            >
              Try again
            </Button>
          )}
        </div>
      )}

      {doc.safety_report && (
        <div className="mt-4" aria-live="polite">
          {doc.safety_report.status === "PASS" ? (
            <p className="text-[15px] font-medium text-accent">
              Safety check passed
              {doc.safety_report.warnings?.includes("NO_ENTITIES_FOUND")
                ? " — no personal details were found automatically; please double-check the page."
                : " — personal details are hidden and ready for your review."}
            </p>
          ) : (
            <div
              role="alert"
              className="rounded border-2 border-danger bg-danger-tint p-4 text-[15px] text-danger"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2 font-semibold">
                  <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />
                  <span>
                    Safety check paused sending ({findings.length} item
                    {findings.length === 1 ? "" : "s"} need review). Highlight the red lines on the
                    left page and replace them to continue.
                  </span>
                </div>

                {hasSafetyIssues && (
                  <button
                    type="button"
                    onClick={handleCycleJump}
                    className="inline-flex h-11 items-center gap-2 rounded border-2 border-danger bg-bg px-4 text-sm font-semibold text-danger shadow-sm hover:bg-danger hover:text-white"
                  >
                    <ArrowDownCircle className="h-4 w-4" aria-hidden="true" />
                    <span>
                      Jump to red issue{" "}
                      {activeFindingIdx !== null
                        ? `(${((activeFindingIdx + 1) % findings.length) + 1}/${findings.length})`
                        : `(1/${findings.length})`}
                    </span>
                  </button>
                )}
              </div>

              {hasSafetyIssues && (
                <ul className="mt-3 space-y-2 border-t border-danger/20 pt-3 text-sm">
                  {findings.map((f, i) => (
                    <li
                      key={`${f.start}-${i}`}
                      className="flex flex-wrap items-center justify-between gap-2"
                    >
                      <span>
                        <strong>{f.type}:</strong> {f.reason}
                        {f.snippet ? ` ("${f.snippet}")` : ""}
                      </span>
                      <button
                        type="button"
                        onClick={() => jumpToIssue(i)}
                        className="inline-flex h-9 items-center gap-1 rounded border border-danger bg-bg px-3.5 text-xs font-semibold text-danger hover:bg-danger hover:text-white"
                      >
                        Jump to line
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Explainability panel */}
      {showWhy && (
        <section className="mt-4 rounded border border-border bg-bg p-4">
          <h2 className="text-base font-semibold text-text">Why were these details hidden?</h2>
          {doc.entities.length === 0 ? (
            <p className="mt-2 text-sm text-text-muted">
              No hidden labels were recorded for this document.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table aria-label="Hidden details explanation" className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-y border-border bg-bg-subtle text-xs text-text-muted">
                    <th className="px-2 py-2">Safe label</th>
                    <th className="px-2 py-2">Category</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Times hidden</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {doc.entities.map((ent) => (
                    <tr key={ent.id}>
                      <td className="px-2 py-2 font-medium text-accent">{ent.token}</td>
                      <td className="px-2 py-2 text-text">{ent.entity_type}</td>
                      <td className="px-2 py-2 text-text-muted">{ent.reason}</td>
                      <td className="px-2 py-2 text-text-muted">{ent.occurrences}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Mobile pane tabs (< 1024px) */}
      <div className="mt-6 flex border-b border-border lg:hidden" role="tablist">
        {(
          [
            { id: "cleaned", label: "Cleaned page" },
            { id: "original", label: "Original page" },
            { id: "result", label: "Draft" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={mobileTab === tab.id}
            onClick={() => setMobileTab(tab.id)}
            className={`flex-1 border-b-2 py-2.5 text-sm font-medium ${
              mobileTab === tab.id
                ? "border-accent text-accent"
                : "border-transparent text-text-muted"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 50/50 PDF-Style Document Split View: Left = Modified/Cleaned PDF sheet, Right = Original PDF sheet */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Left 50%: Modified / Cleaned PDF sheet */}
        <section
          aria-label="Cleaned document preview"
          className={`flex h-[640px] flex-col overflow-hidden rounded border bg-[#EAEDF1] ${
            hasSafetyIssues ? "border-danger" : "border-[#D1D5DB]"
          } ${mobileTab === "cleaned" ? "flex" : "hidden lg:flex"}`}
        >
          {/* PDF Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#D1D5DB] bg-bg px-4 py-2.5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded bg-accent-tint text-accent">
                <FileText className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-xs font-semibold text-text">
                  Cleaned document (Modified)
                </h2>
                <p className="text-[11px] text-text-muted">
                  Highlight any word on the page to hide it everywhere
                </p>
              </div>
            </div>
            {hasSafetyIssues ? (
              <button
                type="button"
                onClick={handleCycleJump}
                className="inline-flex h-9 items-center gap-1.5 rounded border-2 border-danger bg-bg px-3.5 text-xs font-semibold text-danger hover:bg-danger hover:text-white"
              >
                <ArrowDownCircle className="h-4 w-4" aria-hidden="true" />
                <span>Jump to issue ({findings.length})</span>
              </button>
            ) : (
              <span className="rounded bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-text-muted border border-border">
                {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
              </span>
            )}
          </div>

          {selectedText && (
            <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent-tint px-4 py-2.5 text-xs">
              <span className="max-w-[180px] truncate font-semibold text-text" title={selectedText}>
                Hide &ldquo;{selectedText}&rdquo; as
              </span>
              <select
                aria-label="Category"
                value={markType}
                onChange={(e) => setMarkType(e.target.value)}
                className="h-8 rounded border border-border bg-bg px-2 text-xs text-text"
              >
                {MARK_TYPES.map((mt) => (
                  <option key={mt.value} value={mt.value}>
                    {mt.label}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                loading={markMutation.isPending}
                onClick={() => markMutation.mutate()}
              >
                Hide everywhere
              </Button>
            </div>
          )}

          {/* PDF Viewer Canvas + White Paper Sheet */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-5">
            <div
              ref={cleanedRef}
              onMouseUp={handleCleanedMouseUp}
              className="mx-auto min-h-full w-full rounded-[2px] border border-[#D1D5DB] bg-white px-6 py-7 text-[15px] text-text shadow-[0_2px_10px_rgba(17,24,39,0.08)] sm:px-8"
            >
              <div className="mb-5 flex items-center justify-between border-b border-border pb-2.5 text-[11px] text-text-muted">
                <span className="truncate font-medium text-text">{doc.original_filename}</span>
                <span className="shrink-0 uppercase tracking-wide text-accent">Privacy-safe copy</span>
              </div>
              {sanLoading ? (
                <PaneSkeleton />
              ) : sanitizedData ? (
                <div className="break-words font-sans">
                  {renderModifiedPdfLines(sanitizedData.sanitized_text, findings, activeFindingIdx)}
                </div>
              ) : (
                <p className="text-sm text-text-muted">Cleaned document is not available.</p>
              )}
            </div>
          </div>
        </section>

        {/* Right 50%: Original Document PDF sheet */}
        <section
          aria-label="Original document preview"
          className={`flex h-[640px] flex-col overflow-hidden rounded border border-[#D1D5DB] bg-[#EAEDF1] ${
            mobileTab === "original" ? "flex" : "hidden lg:flex"
          }`}
        >
          {/* PDF Toolbar */}
          <div className="flex items-center justify-between border-b border-[#D1D5DB] bg-bg px-4 py-2.5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded bg-bg-subtle text-text-muted border border-border">
                <FileText className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-xs font-semibold text-text">Original document</h2>
                <p className="text-[11px] text-text-muted">
                  Kept only in temporary private memory
                </p>
              </div>
            </div>
            <div className="flex gap-1 rounded bg-bg-subtle p-0.5 text-xs border border-border">
              <button
                type="button"
                onClick={() => setOriginalTab("text")}
                className={`rounded px-2.5 py-1 ${
                  originalTab === "text"
                    ? "bg-bg font-semibold text-accent shadow-sm"
                    : "text-text-muted hover:text-text"
                }`}
              >
                Page view
              </button>
              <button
                type="button"
                onClick={() => setOriginalTab("file")}
                className={`rounded px-2.5 py-1 ${
                  originalTab === "file"
                    ? "bg-bg font-semibold text-accent shadow-sm"
                    : "text-text-muted hover:text-text"
                }`}
              >
                Original file
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 sm:p-5">
            {doc.vault_expired ? (
              <div className="mx-auto flex min-h-full w-full items-center justify-center rounded-[2px] border border-[#D1D5DB] bg-white p-8 text-center shadow-[0_2px_10px_rgba(17,24,39,0.08)]">
                <p className="max-w-xs text-sm text-text-muted">
                  Original details have expired and were removed from temporary private memory.
                </p>
              </div>
            ) : originalTab === "file" ? (
              fileLoading ? (
                <div className="mx-auto min-h-full w-full rounded-[2px] border border-[#D1D5DB] bg-white p-6 shadow-[0_2px_10px_rgba(17,24,39,0.08)]">
                  <PaneSkeleton />
                </div>
              ) : filePreview ? (
                filePreview.mime.startsWith("image/") ? (
                  <div className="mx-auto flex min-h-full w-full items-center justify-center rounded-[2px] border border-[#D1D5DB] bg-white p-4 shadow-[0_2px_10px_rgba(17,24,39,0.08)]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={filePreview.url}
                      alt="Original uploaded file"
                      className="max-h-full max-w-full object-contain"
                    />
                  </div>
                ) : (
                  <iframe
                    title="Original PDF preview"
                    src={filePreview.url}
                    className="h-full w-full rounded-[2px] border border-[#D1D5DB] bg-white shadow-[0_2px_10px_rgba(17,24,39,0.08)]"
                  />
                )
              ) : (
                <div className="mx-auto flex min-h-full w-full items-center justify-center rounded-[2px] border border-[#D1D5DB] bg-white p-8 text-center shadow-[0_2px_10px_rgba(17,24,39,0.08)]">
                  <p className="text-sm text-text-muted">Original file preview unavailable.</p>
                </div>
              )
            ) : (
              <div className="mx-auto min-h-full w-full rounded-[2px] border border-[#D1D5DB] bg-white px-6 py-7 text-[15px] text-text shadow-[0_2px_10px_rgba(17,24,39,0.08)] sm:px-8">
                <div className="mb-5 flex items-center justify-between border-b border-border pb-2.5 text-[11px] text-text-muted">
                  <span className="truncate font-medium text-text">{doc.original_filename}</span>
                  <span className="shrink-0 uppercase tracking-wide">Original copy</span>
                </div>
                {origLoading ? (
                  <PaneSkeleton />
                ) : originalData ? (
                  <div className="font-sans">
                    {renderFormattedOriginal(originalData.original_text, originalData.highlights)}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted">Original text unavailable.</p>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Dedicated Full-Width Generated Report Sheet below 50/50 split */}
      <section
        ref={resultSectionRef}
        aria-label="Generated draft result"
        className={`mt-6 overflow-hidden rounded border border-[#D1D5DB] bg-[#EAEDF1] ${
          mobileTab === "result" ? "block" : "hidden lg:block"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#D1D5DB] bg-bg px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-text">Generated draft</h2>
            <p className="text-xs text-text-muted">
              Only the cleaned page on the left is sent to the AI assistant; real patient details
              are restored here on your screen.
            </p>
          </div>
          {doc.status === "COMPLETED" && resultData && (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="sm" onClick={handleCopy}>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                Copy
              </Button>
              <Button variant="secondary" size="sm" onClick={() => handleExport("txt")}>
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Download .txt
              </Button>
              <Button variant="secondary" size="sm" onClick={() => handleExport("docx")}>
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Download .docx
              </Button>
            </div>
          )}
        </div>

        <div className="p-4 sm:p-6">
          <div className="mx-auto max-w-4xl rounded-[2px] border border-[#D1D5DB] bg-white px-6 py-7 shadow-[0_2px_10px_rgba(17,24,39,0.08)] sm:px-10 sm:py-8">
            {doc.status === "SENDING" ? (
              <BrandLoader label="Writing clinical draft (Step 6 of 6)…" />
            ) : doc.status === "LLM_FAILED" ? (
              <div role="alert" className="rounded bg-danger-tint p-4 text-sm text-danger">
                <p className="font-medium">Could not write the draft right now.</p>
                <div className="mt-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={retryMutation.isPending}
                    onClick={() => retryMutation.mutate()}
                  >
                    Try again
                  </Button>
                </div>
              </div>
            ) : doc.status === "COMPLETED" && resultData ? (
              <div>
                {resultData.fallback_used && (
                  <p className="mb-3 rounded bg-bg-subtle px-3 py-2 text-xs text-text-muted">
                    Completed automatically using the backup AI writing service (
                    {resultData.llm_provider_used}).
                  </p>
                )}
                {resultData.vault_expired && (
                  <p className="mb-3 rounded bg-bg-subtle px-3 py-2 text-xs text-text-muted">
                    Original details have expired, so safe labels are shown instead.
                  </p>
                )}
                {resultData.warnings.length > 0 && (
                  <p className="mb-3 rounded bg-bg-subtle px-3 py-2 text-xs text-text-muted">
                    Unrecognized labels left as written:{" "}
                    {resultData.warnings.map((w) => w.token).join(", ")}
                  </p>
                )}
                <div className="font-sans">{renderCleanDraftPdf(resultData.text)}</div>
              </div>
            ) : (
              <p className="text-sm text-text-muted">
                Review the cleaned document on the left against the original on the right, then
                press &ldquo;Approve and generate&rdquo; below.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Sticky bottom action bar */}
      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-[#D1D5DB] bg-bg py-3 shadow-[0_-2px_8px_rgba(17,24,39,0.08)]">
        <div className="mx-auto flex max-w-app items-center justify-between gap-3 px-4 sm:px-6">
          <Button
            variant="destructive"
            size="sm"
            loading={deleteMutation.isPending}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete document
          </Button>

          <Button
            disabled={!canApproveAndSend}
            loading={approveAndSendMutation.isPending}
            onClick={() => approveAndSendMutation.mutate()}
          >
            Approve and generate
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete document"
        message={`Permanently delete "${doc.original_filename}" and clear its temporary private memory?`}
        confirmLabel="Delete"
        destructive
        loading={deleteMutation.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </div>
  );
}

export default function DocumentReviewPage() {
  return (
    <AppLayout allowedRoles={["doctor"]} bottomPaddingClass="pb-20">
      <DocumentReviewContent />
    </AppLayout>
  );
}
