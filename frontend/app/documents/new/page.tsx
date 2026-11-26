"use client";

import { useQuery } from "@tanstack/react-query";
import { Camera, FileText, RefreshCw, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { ApiError, apiRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatBytes } from "@/lib/format";
import type { DocumentDetail, TaskType } from "@/lib/types";

const TASK_OPTIONS: Array<{ value: TaskType; label: string; hint: string }> = [
  {
    value: "discharge_summary",
    label: "Discharge summary",
    hint: "Summarize the hospital stay, key findings, medications, and follow-up plan.",
  },
  {
    value: "case_summary",
    label: "Case summary",
    hint: "Create a clear overview of the patient history, exam results, and assessment.",
  },
  {
    value: "treatment_plan",
    label: "Treatment plan",
    hint: "Draft next-step care instructions, medications, and monitoring notes.",
  },
];

const LIVE_STEPS = [
  { key: "EXTRACT", label: "Reading your file" },
  { key: "DETECT", label: "Finding personal details" },
  { key: "TOKENIZE", label: "Hiding personal details" },
  { key: "SAFETY_CHECK", label: "Safety check" },
];

const ACCEPTED_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/svg+xml",
]);

const ACCEPTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".svg"];

function isSupportedFile(file: File): boolean {
  if (ACCEPTED_MIME_TYPES.has(file.type)) return true;
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isImageFile(file: File): boolean {
  if (file.type.startsWith("image/")) return true;
  const lower = file.name.toLowerCase();
  return [".png", ".jpg", ".jpeg", ".svg"].some((ext) => lower.endsWith(ext));
}

function NewDocumentContent() {
  const router = useRouter();
  const { user } = useAuth();
  const isRestricted = user?.status === "restricted";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mobileCameraInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [taskType, setTaskType] = useState<TaskType>("discharge_summary");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<{
    message: string;
    existingDocumentId?: string;
  } | null>(null);
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);

  // Camera state
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");

  const stopCameraStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraReady(false);
  }, []);

  useEffect(() => {
    return () => {
      stopCameraStream();
    };
  }, [stopCameraStream]);

  useEffect(() => {
    if (!selectedFile || !isImageFile(selectedFile)) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [selectedFile]);

  const startCamera = useCallback(
    async (mode: "environment" | "user") => {
      setCameraError(null);
      setCameraOpen(true);
      setCameraReady(false);
      stopCameraStream();

      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        setCameraError(
          "Live camera preview is not available in this browser. Use the device camera button below to take or pick a photo.",
        );
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: mode },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setCameraReady(true);
      } catch (err) {
        const name = err instanceof DOMException ? err.name : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          setCameraError(
            "Camera access was blocked. Please allow camera permission in your browser address bar, or upload a photo file instead.",
          );
        } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
          setCameraError(
            "No camera was found on this device. You can upload a PDF, PNG, JPG, or SVG file instead.",
          );
        } else {
          setCameraError(
            "Could not open the camera right now. Please try again or choose an image file from your device.",
          );
        }
      }
    },
    [stopCameraStream],
  );

  const handleCloseCamera = () => {
    stopCameraStream();
    setCameraOpen(false);
    setCameraError(null);
  };

  const handleToggleCamera = () => {
    const nextMode = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextMode);
    void startCamera(nextMode);
  };

  const handleCapturePhoto = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
      setCameraError("Camera is still starting. Please wait a moment and try again.");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setCameraError("Could not capture image in this browser.");
      return;
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError("Could not save the captured photo. Please try again.");
          return;
        }
        const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        const photoFile = new File([blob], `camera-photo-${timestamp}.png`, {
          type: "image/png",
        });
        handleFilePick(photoFile);
        handleCloseCamera();
      },
      "image/png",
      0.95,
    );
  };

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
    if (!isSupportedFile(file)) {
      setUploadError({
        message: "Please choose a PDF, PNG, JPG, or SVG file.",
      });
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError({ message: "File exceeds the maximum allowed size of 10 MB." });
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError({ message: "Select a file or take a photo before continuing." });
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
      <p className="mt-1.5 text-[15px] text-text-muted">
        Upload a PDF or image (PNG, JPG, SVG), or take a photo with your camera. Personal details
        are hidden automatically before you review the page.
      </p>

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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-text">Cleaning your document</h2>
              <p className="mt-1 text-[15px] text-text-muted">
                Reading the page, finding personal details, replacing them with safe labels, and
                running a safety check.
              </p>
            </div>
            <span className="rounded bg-accent-tint px-2.5 py-1 text-xs font-semibold text-accent">
              Step{" "}
              {Math.min(
                LIVE_STEPS.length,
                LIVE_STEPS.filter(
                  (m) => liveDoc?.steps.find((s) => s.step === m.key)?.status === "succeeded",
                ).length + 1,
              )}{" "}
              of {LIVE_STEPS.length}
            </span>
          </div>

          <ol className="mt-6 space-y-3">
            {LIVE_STEPS.map((stepMeta, idx) => {
              const stepRow = liveDoc?.steps.find((s) => s.step === stepMeta.key);
              const status = stepRow?.status || "pending";
              const prevDone =
                idx === 0 ||
                liveDoc?.steps.find((s) => s.step === LIVE_STEPS[idx - 1].key)?.status ===
                  "succeeded";
              const isCurrent = status === "running" || (status === "pending" && prevDone);
              const isNext =
                status === "pending" &&
                idx > 0 &&
                (liveDoc?.steps.find((s) => s.step === LIVE_STEPS[idx - 1].key)?.status ===
                  "running" ||
                  (idx === 1 &&
                    liveDoc?.steps.find((s) => s.step === LIVE_STEPS[0].key)?.status ===
                      "pending"));

              return (
                <li
                  key={stepMeta.key}
                  className={`flex items-center justify-between gap-3 rounded border px-4 py-3 text-sm ${
                    status === "failed"
                      ? "border-danger bg-danger-tint"
                      : isCurrent
                        ? "border-accent bg-accent-tint/60"
                        : "border-border bg-bg"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                        status === "succeeded"
                          ? "bg-accent text-white"
                          : status === "failed"
                            ? "bg-danger text-white"
                            : isCurrent
                              ? "border-2 border-accent bg-bg text-accent"
                              : "border border-border bg-bg-subtle text-text-muted"
                      }`}
                    >
                      {status === "succeeded" ? (
                        <svg aria-hidden="true" className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none">
                          <path
                            className="cs-check-draw"
                            d="M3 8.5L6.5 12L13 4.5"
                            stroke="currentColor"
                            strokeWidth="2.2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      ) : status === "running" ? (
                        <svg aria-hidden="true" className="cs-spinner h-3.5 w-3.5" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
                          <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                      ) : (
                        idx + 1
                      )}
                    </span>
                    <span
                      className={
                        status === "failed"
                          ? "font-semibold text-danger"
                          : isCurrent || status === "succeeded"
                            ? "font-semibold text-text"
                            : "text-text-muted"
                      }
                    >
                      {stepMeta.label}
                    </span>
                  </div>

                  <span className="text-xs font-medium">
                    {status === "succeeded" ? (
                      <span className="text-accent">Done</span>
                    ) : status === "failed" ? (
                      <span className="text-danger">Failed</span>
                    ) : isCurrent ? (
                      <span className="rounded bg-accent px-2 py-0.5 text-white">Current</span>
                    ) : isNext ? (
                      <span className="rounded bg-bg-subtle px-2 py-0.5 text-text-muted">Next</span>
                    ) : (
                      <span className="text-text-muted">Pending</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      ) : (
        <form onSubmit={handleUpload} className="mt-8 space-y-6">
          <fieldset>
            <legend className="text-xs font-medium text-text">What would you like to write?</legend>
            <div className="mt-2 space-y-2">
              {TASK_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-start gap-3 rounded border px-3.5 py-3 text-sm transition-colors ${
                    taskType === opt.value
                      ? "border-accent bg-accent-tint/40 text-text"
                      : "border-border bg-bg text-text hover:bg-bg-subtle"
                  }`}
                >
                  <input
                    type="radio"
                    name="task_type"
                    value={opt.value}
                    checked={taskType === opt.value}
                    onChange={() => setTaskType(opt.value)}
                    disabled={isRestricted}
                    className="mt-0.5 h-4 w-4 accent-accent"
                  />
                  <div>
                    <span className="font-medium">{opt.label}</span>
                    <p className="mt-0.5 text-xs text-text-muted">{opt.hint}</p>
                  </div>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="document-file-input" className="block text-xs font-medium text-text">
                Patient document or photo
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={isRestricted}
                  onClick={() => void startCamera(facingMode)}
                >
                  <Camera className="h-4 w-4 text-accent" aria-hidden="true" />
                  Take photo with camera
                </Button>
                <input
                  ref={mobileCameraInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  disabled={isRestricted}
                  onChange={(e) => handleFilePick(e.target.files?.[0] || null)}
                  className="sr-only"
                  aria-label="Take photo with device camera"
                />
              </div>
            </div>

            {/* Inline live camera viewfinder */}
            {cameraOpen && (
              <div
                className="mt-3 overflow-hidden rounded border border-accent bg-bg p-4"
                aria-label="Camera capture"
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-text">Take a clear photo of the page</p>
                    <p className="text-xs text-text-muted">
                      Hold the page flat in good lighting so all text is easy to read.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleCloseCamera}
                    aria-label="Close camera"
                    className="rounded p-1.5 text-text-muted hover:bg-bg-subtle hover:text-text"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {cameraError ? (
                  <div className="space-y-3 rounded bg-danger-tint p-3.5 text-xs text-danger">
                    <p>{cameraError}</p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => mobileCameraInputRef.current?.click()}
                      >
                        <Camera className="h-3.5 w-3.5" />
                        Use device camera / gallery
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={handleCloseCamera}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="relative overflow-hidden rounded border border-border bg-[#111827]">
                      <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="max-h-[360px] w-full object-contain"
                      />
                      {!cameraReady && (
                        <div className="absolute inset-0 flex items-center justify-center bg-[#111827]/70 text-xs text-white">
                          Waiting for camera permission…
                        </div>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={handleToggleCamera}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Switch camera
                      </Button>
                      <div className="flex items-center gap-2">
                        <Button type="button" variant="ghost" size="sm" onClick={handleCloseCamera}>
                          Cancel
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          disabled={!cameraReady}
                          onClick={handleCapturePhoto}
                        >
                          <Camera className="h-4 w-4" />
                          Capture photo
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Drag and drop file area */}
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
              className={`mt-2 flex cursor-pointer flex-col items-center justify-center rounded border border-dashed px-6 py-8 text-center transition-colors ${
                isDragging ? "border-accent bg-accent-tint" : "border-border bg-bg hover:bg-bg-subtle"
              }`}
            >
              {previewUrl ? (
                <div className="flex flex-col items-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previewUrl}
                    alt="Selected document preview"
                    className="max-h-44 rounded border border-border bg-bg object-contain shadow-sm"
                  />
                  <p className="mt-3 text-sm font-medium text-text">{selectedFile?.name}</p>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {selectedFile ? formatBytes(selectedFile.size) : ""} · Click to choose a
                    different file
                  </p>
                </div>
              ) : selectedFile ? (
                <div className="flex flex-col items-center">
                  <FileText aria-hidden="true" className="h-8 w-8 text-accent" />
                  <p className="mt-2 text-sm font-medium text-text">{selectedFile.name}</p>
                  <p className="mt-1 text-xs text-text-muted">
                    {formatBytes(selectedFile.size)} · Click to choose a different file
                  </p>
                </div>
              ) : (
                <>
                  <Upload aria-hidden="true" className="h-6 w-6 text-text-muted" />
                  <p className="mt-2 text-sm font-medium text-text">
                    Click or drag a document or image here
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    Supports PDF, PNG, JPG, and SVG · up to 10 MB (PDFs up to 30 pages)
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                id="document-file-input"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.svg,application/pdf,image/png,image/jpeg,image/svg+xml"
                disabled={isRestricted}
                onChange={(e) => handleFilePick(e.target.files?.[0] || null)}
                className="sr-only"
              />
            </div>

            {selectedFile && (
              <div className="mt-2 flex items-center justify-end gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => void startCamera(facingMode)}
                  className="font-medium text-accent hover:underline"
                >
                  Retake with camera
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null);
                    setUploadError(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="font-medium text-text-muted hover:text-danger"
                >
                  Clear selection
                </button>
              </div>
            )}
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
