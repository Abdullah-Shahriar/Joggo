"use client";

import { useQuery } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { ApiError, apiRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatBytes } from "@/lib/format";
import type { DocumentDetail, TaskType } from "@/lib/types";

const TASK_OPTIONS: Array<{ value: TaskType; label: string }> = [
  { value: "discharge_summary", label: "Discharge summary" },
  { value: "case_summary", label: "Case summary" },
  { value: "treatment_plan", label: "Treatment plan" },
];

const LIVE_STEPS = [
  { key: "EXTRACT", label: "Reading file" },
  { key: "DETECT", label: "Finding identifiers" },
  { key: "TOKENIZE", label: "Replacing with placeholders" },
  { key: "SAFETY_CHECK", label: "Safety check" },
];

function NewDocumentContent() {
  const router = useRouter();
  const { user } = useAuth();
  const isRestricted = user?.status === "restricted";
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [taskType, setTaskType] = useState<TaskType>("discharge_summary");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<{
    message: string;
    existingDocumentId?: string;
  } | null>(null);
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);

  const { data: liveDoc } = useQuery<DocumentDetail>({
    queryKey: ["document", uploadedDocId],
    queryFn: () => apiRequest<DocumentDetail>(`/documents/${uploadedDocId}`),
    enabled: Boolean(uploadedDocId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "UPLOADED" || status === "PROCESSING") {
        return 1500;
      }
      return false;
    },
  });

  useEffect(() => {
    if (liveDoc && liveDoc.status !== "UPLOADED" && liveDoc.status !== "PROCESSING") {
      router.replace(`/documents/${liveDoc.id}`);
    }
  }, [liveDoc, router]);

  const handleFilePick = (file: File | null) => {
    setUploadError(null);
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setUploadError({ message: "File exceeds the maximum allowed size of 10 MB." });
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError({ message: "Select a PDF file before continuing." });
      return;
    }
    setSubmitting(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("task_type", taskType);
      const res = await apiRequest<{ id: string; status: string }>("/documents", {
        method: "POST",
        body: formData,
        silentErrorToast: true,
      });
      setUploadedDocId(res.id);
    } catch (err) {
      if (err instanceof ApiError) {
        setUploadError({
          message: err.message,
          existingDocumentId: err.existingDocumentId,
        });
      } else {
        setUploadError({ message: "Upload failed. Please try again." });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-form">
      <h1 className="text-[28px] font-semibold text-text">New document</h1>

      {isRestricted && (
        <div role="alert" className="mt-4 rounded bg-danger-tint px-4 py-3 text-sm text-danger">
          Your account is restricted. You can contact support from{" "}
          <Link href="/help" className="font-medium underline">
            Help
          </Link>
          .
        </div>
      )}

      {uploadedDocId ? (
        <section className="mt-8 rounded border border-border bg-bg p-6" aria-live="polite">
          <h2 className="text-base font-semibold text-text">Cleaning your document</h2>
          <p className="mt-1 text-xs text-text-muted">
            Running local extraction, identifier detection, tokenization, and safety checks.
          </p>
          <ol className="mt-6 space-y-3">
            {LIVE_STEPS.map((stepMeta) => {
              const stepRow = liveDoc?.steps.find((s) => s.step === stepMeta.key);
              const status = stepRow?.status || "pending";
              return (
                <li key={stepMeta.key} className="flex items-center gap-3 text-sm">
                  {status === "succeeded" ? (
                    <svg
                      aria-hidden="true"
                      className="h-4 w-4 text-accent"
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
                  ) : status === "running" ? (
                    <svg
                      aria-hidden="true"
                      className="cs-spinner h-4 w-4 text-accent"
                      viewBox="0 0 16 16"
                      fill="none"
                    >
                      <circle cx="8" cy="8" r="6" stroke="#E5E7EB" strokeWidth="2" />
                      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  ) : status === "failed" ? (
                    <span className="h-2.5 w-2.5 rounded-full bg-danger" />
                  ) : (
                    <span className="h-2.5 w-2.5 rounded-full bg-border" />
                  )}
                  <span
                    className={
                      status === "succeeded" || status === "running"
                        ? "font-medium text-text"
                        : status === "failed"
                          ? "font-medium text-danger"
                          : "text-text-muted"
                    }
                  >
                    {stepMeta.label}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      ) : (
        <form onSubmit={handleUpload} className="mt-8 space-y-6">
          <fieldset>
            <legend className="text-xs font-medium text-text">Task type</legend>
            <div className="mt-2 space-y-2">
              {TASK_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className="flex cursor-pointer items-center gap-3 rounded border border-border px-3 py-2.5 text-sm text-text hover:bg-bg-subtle"
                >
                  <input
                    type="radio"
                    name="task_type"
                    value={opt.value}
                    checked={taskType === opt.value}
                    onChange={() => setTaskType(opt.value)}
                    disabled={isRestricted}
                    className="h-4 w-4 accent-accent"
                  />
                  <span>{opt.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="pdf-file-input" className="block text-xs font-medium text-text">
              Patient PDF
            </label>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                handleFilePick(e.dataTransfer.files?.[0] || null);
              }}
              onClick={() => !isRestricted && fileInputRef.current?.click()}
              className={`mt-2 flex cursor-pointer flex-col items-center justify-center rounded border border-dashed px-6 py-10 text-center transition-colors ${
                isDragging ? "border-accent bg-accent-tint" : "border-border bg-bg hover:bg-bg-subtle"
              }`}
            >
              <Upload aria-hidden="true" className="h-6 w-6 text-text-muted" />
              <p className="mt-2 text-sm font-medium text-text">
                {selectedFile ? selectedFile.name : "Click or drag a PDF here"}
              </p>
              <p className="mt-1 text-xs text-text-muted">
                {selectedFile
                  ? formatBytes(selectedFile.size)
                  : "PDF, up to 10 MB and 30 pages"}
              </p>
              <input
                ref={fileInputRef}
                id="pdf-file-input"
                type="file"
                accept="application/pdf,.pdf"
                disabled={isRestricted}
                onChange={(e) => handleFilePick(e.target.files?.[0] || null)}
                className="sr-only"
              />
            </div>
          </div>

          <p className="text-xs text-text-muted">Demo environment — use synthetic data only</p>

          {uploadError && (
            <div role="alert" className="rounded bg-danger-tint px-3.5 py-2.5 text-xs text-danger">
              <p>{uploadError.message}</p>
              {uploadError.existingDocumentId && (
                <Link
                  href={`/documents/${uploadError.existingDocumentId}`}
                  className="mt-1 inline-block font-medium text-accent underline"
                >
                  Open existing document
                </Link>
              )}
            </div>
          )}

          <Button type="submit" loading={submitting} disabled={isRestricted || !selectedFile}>
            Upload and clean
          </Button>
        </form>
      )}
    </div>
  );
}

export default function NewDocumentPage() {
  return (
    <AppLayout allowedRoles={["doctor"]}>
      <NewDocumentContent />
    </AppLayout>
  );
}
