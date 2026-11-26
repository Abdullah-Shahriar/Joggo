"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, HelpCircle, Trash2 } from "lucide-react";
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
  { value: "FACILITY", label: "Facility" },
  { value: "OTHER", label: "Other" },
] as const;

const TRACKER_STAGES = ["Extract", "Detect", "Tokenize", "Safety", "Review", "Generate"];

const TOKEN_SPLIT_RE =
  /(\[(?:PATIENT|DOCTOR|PERSON|PHONE|EMAIL|ID|MRN|LOCATION|FACILITY|URL|IP|OTHER|DAY)_[A-Z0-9?-]+\]|\bAge\s+(?:\d{1,2}|90\+)|\b90\+\s+years)/g;

function renderHighlightedOriginal(
  text: string,
  highlights: OriginalTextResponse["highlights"],
) {
  if (!highlights.length) return text;
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

  return parts.map((p) =>
    p.highlighted ? (
      <mark key={p.key} title={p.token} className="rounded bg-accent-tint px-0.5 text-text">
        {p.content}
      </mark>
    ) : (
      <Fragment key={p.key}>{p.content}</Fragment>
    ),
  );
}

function renderTokenizedText(text: string, jumpOffset: number | null) {
  const segments = text.split(TOKEN_SPLIT_RE);
  let offset = 0;
  return segments.map((seg, idx) => {
    const start = offset;
    offset += seg.length;
    const isToken = TOKEN_SPLIT_RE.test(seg);
    TOKEN_SPLIT_RE.lastIndex = 0;
    const isJumpTarget = jumpOffset !== null && jumpOffset >= start && jumpOffset < offset;

    if (isToken) {
      return (
        <span
          key={`${idx}-${start}`}
          className="rounded bg-accent-tint px-1 font-medium text-accent"
        >
          {seg}
        </span>
      );
    }
    if (isJumpTarget) {
      return (
        <mark key={`${idx}-${start}`} id="safety-jump-target" className="rounded bg-danger-tint px-0.5 text-danger">
          {seg}
        </mark>
      );
    }
    return <Fragment key={`${idx}-${start}`}>{seg}</Fragment>;
  });
}

function DocumentReviewContent() {
  const params = useParams<{ id: string }>();
  const docId = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [mobileTab, setMobileTab] = useState<"original" | "cleaned" | "result">("cleaned");
  const [originalTab, setOriginalTab] = useState<"text" | "pdf">("text");
  const [showWhy, setShowWhy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [jumpOffset, setJumpOffset] = useState<number | null>(null);

  // Highlight-to-tokenize selection state
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

  const canLoadText = Boolean(
    doc && !["UPLOADED", "PROCESSING"].includes(doc.status),
  );

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

  // Load PDF blob only when user switches to PDF preview tab and vault is alive
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    if (originalTab !== "pdf" || !doc || doc.vault_expired) {
      return;
    }
    setPdfLoading(true);
    apiBlob(`/documents/${docId}/original-pdf`, { silentErrorToast: true })
      .then(({ blob }) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      })
      .catch(() => {
        if (active) setPdfUrl(null);
      })
      .finally(() => {
        if (active) setPdfLoading(false);
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
      emitToast({ kind: "success", message: "Marked and replaced everywhere." });
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
      emitToast({ kind: "success", message: "Document deleted." });
      router.replace("/documents");
    },
  });

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

  const activeStageIndex = useMemo(() => {
    if (!doc) return 0;
    if (doc.status === "COMPLETED") return 6;
    if (doc.status === "SENDING" || doc.status === "LLM_FAILED") return 5;
    if (doc.status === "APPROVED" || doc.status === "REVIEW_REQUIRED" || doc.status === "BLOCKED") {
      return 4;
    }
    return 1;
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

  const safetyPass = doc.safety_report?.status === "PASS";
  const vaultExpiredBeforeApproval =
    doc.vault_expired && ["BLOCKED", "REVIEW_REQUIRED", "APPROVED", "FAILED"].includes(doc.status);
  const canApproveAndSend =
    safetyPass &&
    !vaultExpiredBeforeApproval &&
    (doc.status === "REVIEW_REQUIRED" || doc.status === "APPROVED") &&
    Boolean(sanitizedData?.sanitized_sha256);

  return (
    <div className="pb-20">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-text">{doc.original_filename}</h1>
          <DocumentStatusBadge status={doc.status} />
        </div>
        <Button variant="secondary" size="sm" onClick={() => setShowWhy((v) => !v)}>
          <HelpCircle className="h-4 w-4" />
          Why was this replaced?
        </Button>
      </div>

      {/* Thin step tracker */}
      <ol aria-label="Document stages" className="mt-4 flex flex-wrap items-center gap-2 text-xs">
        {TRACKER_STAGES.map((label, idx) => {
          const done = idx < activeStageIndex;
          const current = idx === activeStageIndex;
          return (
            <li key={label} className="flex items-center gap-2">
              <span
                className={
                  done
                    ? "font-medium text-accent"
                    : current
                      ? "font-semibold text-text"
                      : "text-text-muted"
                }
              >
                {label}
              </span>
              {idx < TRACKER_STAGES.length - 1 && (
                <span aria-hidden="true" className="text-border">
                  ·
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {/* Banners */}
      {vaultExpiredBeforeApproval && (
        <div role="alert" className="mt-4 rounded bg-danger-tint px-4 py-3 text-sm text-danger">
          Session data expired. Upload the file again.
        </div>
      )}

      {doc.status === "FAILED" && (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded bg-danger-tint px-4 py-3 text-sm text-danger">
          <span>Document processing failed ({doc.failure_code || "ERROR"}).</span>
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
            <p className="text-sm font-medium text-accent">
              Safety check passed
              {doc.safety_report.warnings?.includes("NO_ENTITIES_FOUND")
                ? " — no identifiers were detected; please review carefully."
                : ""}
            </p>
          ) : (
            <div role="alert" className="rounded bg-danger-tint p-4 text-sm text-danger">
              <p className="font-medium">
                Safety check blocked sending. Highlight the text and replace it to continue.
              </p>
              {sanitizedData && sanitizedData.findings.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs">
                  {sanitizedData.findings.map((f, i) => (
                    <li key={`${f.start}-${i}`} className="flex flex-wrap items-center gap-2">
                      <span>
                        {f.type}: {f.reason}
                        {f.snippet ? ` ("${f.snippet}")` : ""}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setMobileTab("cleaned");
                          setJumpOffset(f.start);
                          setTimeout(() => {
                            document
                              .getElementById("safety-jump-target")
                              ?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }, 50);
                        }}
                        className="font-medium text-accent underline"
                      >
                        Jump to
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Explainability panel (A02) */}
      {showWhy && (
        <section className="mt-4 rounded border border-border bg-bg p-4">
          <h2 className="text-sm font-semibold text-text">Why was this replaced?</h2>
          {doc.entities.length === 0 ? (
            <p className="mt-2 text-xs text-text-muted">No placeholders recorded for this document.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table aria-label="Replacement explanations" className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-y border-border bg-bg-subtle text-text-muted">
                    <th className="px-2 py-2">Token</th>
                    <th className="px-2 py-2">Type</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Occurrences</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {doc.entities.map((ent) => (
                    <tr key={ent.id}>
                      <td className="px-2 py-2 font-mono text-accent">{ent.token}</td>
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
        {(["original", "cleaned", "result"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={mobileTab === tab}
            onClick={() => setMobileTab(tab)}
            className={`flex-1 border-b-2 py-2.5 text-sm font-medium capitalize ${
              mobileTab === tab ? "border-accent text-accent" : "border-transparent text-text-muted"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Three bordered panes on desktop */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Pane 1: Original */}
        <section
          className={`flex h-[560px] flex-col rounded border border-border bg-bg ${
            mobileTab === "original" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Original
            </h2>
            <div className="flex gap-1 text-xs">
              <button
                type="button"
                onClick={() => setOriginalTab("text")}
                className={`rounded px-2 py-1 ${
                  originalTab === "text" ? "bg-bg font-medium text-accent" : "text-text-muted"
                }`}
              >
                Text
              </button>
              <button
                type="button"
                onClick={() => setOriginalTab("pdf")}
                className={`rounded px-2 py-1 ${
                  originalTab === "pdf" ? "bg-bg font-medium text-accent" : "text-text-muted"
                }`}
              >
                PDF preview
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 text-sm leading-relaxed">
            {doc.vault_expired ? (
              <p className="text-xs text-text-muted">
                Original details have expired and were removed from temporary memory.
              </p>
            ) : originalTab === "pdf" ? (
              pdfLoading ? (
                <PaneSkeleton />
              ) : pdfUrl ? (
                <iframe
                  title="Original PDF preview"
                  src={pdfUrl}
                  className="h-full w-full border-0"
                />
              ) : (
                <p className="text-xs text-text-muted">PDF preview unavailable.</p>
              )
            ) : origLoading ? (
              <PaneSkeleton />
            ) : originalData ? (
              <div className="whitespace-pre-wrap break-words font-sans text-text">
                {renderHighlightedOriginal(originalData.original_text, originalData.highlights)}
              </div>
            ) : (
              <p className="text-xs text-text-muted">Original text unavailable.</p>
            )}
          </div>
        </section>

        {/* Pane 2: Cleaned text + highlight-to-tokenize */}
        <section
          className={`flex h-[560px] flex-col rounded border border-border bg-bg ${
            mobileTab === "cleaned" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Cleaned text
            </h2>
            <span className="text-[11px] text-text-muted">Select text to replace</span>
          </div>

          {/* Highlight-to-tokenize bar when selection active */}
          {selectedText && (
            <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent-tint px-3 py-2 text-xs">
              <span className="max-w-[140px] truncate font-medium text-text" title={selectedText}>
                Mark &ldquo;{selectedText}&rdquo; as
              </span>
              <select
                aria-label="Entity type"
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
                Replace
              </Button>
            </div>
          )}

          <div
            ref={cleanedRef}
            onMouseUp={handleCleanedMouseUp}
            className="flex-1 overflow-y-auto p-4 text-sm leading-relaxed"
          >
            {sanLoading ? (
              <PaneSkeleton />
            ) : sanitizedData ? (
              <div className="whitespace-pre-wrap break-words text-text">
                {renderTokenizedText(sanitizedData.sanitized_text, jumpOffset)}
              </div>
            ) : (
              <p className="text-xs text-text-muted">Cleaned text is not available.</p>
            )}
          </div>
        </section>

        {/* Pane 3: Result */}
        <section
          className={`flex h-[560px] flex-col rounded border border-border bg-bg ${
            mobileTab === "result" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Result
            </h2>
            {doc.status === "COMPLETED" && resultData && (
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" onClick={handleCopy}>
                  <Copy className="h-3.5 w-3.5" />
                  Copy
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleExport("txt")}>
                  <Download className="h-3.5 w-3.5" />
                  .txt
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleExport("docx")}>
                  <Download className="h-3.5 w-3.5" />
                  .docx
                </Button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 text-sm leading-relaxed">
            {doc.status === "SENDING" ? (
              <BrandLoader label="Generating draft…" />
            ) : doc.status === "LLM_FAILED" ? (
              <div role="alert" className="rounded bg-danger-tint p-4 text-sm text-danger">
                <p>Could not generate a draft.</p>
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
                    Switched to backup provider ({resultData.llm_provider_used}).
                  </p>
                )}
                {resultData.vault_expired && (
                  <p className="mb-3 rounded bg-bg-subtle px-3 py-2 text-xs text-text-muted">
                    Original details have expired, showing placeholders only.
                  </p>
                )}
                {resultData.warnings.length > 0 && (
                  <p className="mb-3 rounded bg-bg-subtle px-3 py-2 text-xs text-text-muted">
                    Unrecognized placeholders left as written:{" "}
                    {resultData.warnings.map((w) => w.token).join(", ")}
                  </p>
                )}
                <div className="whitespace-pre-wrap break-words text-text">{resultData.text}</div>
              </div>
            ) : (
              <p className="text-xs text-text-muted">
                Review the cleaned text and press &ldquo;Approve and generate&rdquo; to create the
                draft.
              </p>
            )}
          </div>
        </section>
      </div>

      {/* Sticky bottom action bar */}
      <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-border bg-bg py-3">
        <div className="mx-auto flex max-w-app items-center justify-between gap-3 px-4 sm:px-6">
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-4 w-4" />
            Delete
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
        message={`Permanently delete "${doc.original_filename}" and wipe its temporary session vault?`}
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
    <AppLayout allowedRoles={["doctor"]}>
      <DocumentReviewContent />
    </AppLayout>
  );
}
