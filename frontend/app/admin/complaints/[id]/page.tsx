"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/FormFields";
import { SimpleStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest, emitToast } from "@/lib/api";
import { formatComplaintCategory, formatDateTime } from "@/lib/format";
import type { ComplaintDetail, ComplaintStatus } from "@/lib/types";

function AdminComplaintDetailContent() {
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const [replyBody, setReplyBody] = useState("");
  const [replyError, setReplyError] = useState<string | null>(null);
  const [flashKey, setFlashKey] = useState<string | null>(null);
  const [shakeHeader, setShakeHeader] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery<ComplaintDetail>({
    queryKey: ["admin", "complaint", params.id],
    queryFn: () => apiRequest<ComplaintDetail>(`/admin/complaints/${params.id}`),
  });

  const triggerFlash = (key: string) => {
    setFlashKey(key);
    setTimeout(() => setFlashKey((prev) => (prev === key ? null : prev)), 1300);
  };

  const replyMutation = useMutation({
    mutationFn: (body: string) =>
      apiRequest<ComplaintDetail>(`/admin/complaints/${params.id}/messages`, {
        method: "POST",
        body: { body },
      }),
    onSuccess: (updated) => {
      setReplyBody("");
      setReplyError(null);
      queryClient.setQueryData(["admin", "complaint", params.id], updated);
      const lastMsg = updated.messages[updated.messages.length - 1];
      if (lastMsg) triggerFlash(lastMsg.id);
      emitToast({ kind: "success", message: "Reply posted." });
    },
    onError: () => {
      setShakeHeader(true);
      setTimeout(() => setShakeHeader(false), 400);
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: ComplaintStatus) =>
      apiRequest<ComplaintDetail>(`/admin/complaints/${params.id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "complaint", params.id], updated);
      triggerFlash("status");
      emitToast({ kind: "success", message: "Complaint status updated." });
    },
    onError: () => {
      setShakeHeader(true);
      setTimeout(() => setShakeHeader(false), 400);
    },
  });

  if (isLoading) return <BrandLoader label="Loading complaint…" />;
  if (isError || !data) {
    return (
      <div className="rounded bg-danger-tint p-4 text-sm text-danger">
        Could not load complaint.{" "}
        <button type="button" onClick={() => refetch()} className="font-medium underline">
          Try again
        </button>
      </div>
    );
  }

  const nextStatuses: ComplaintStatus[] =
    data.status === "open"
      ? ["in_progress", "resolved"]
      : data.status === "in_progress"
        ? ["resolved"]
        : ["in_progress"];

  return (
    <div className="max-w-prose">
      <Link href="/admin/complaints" className="text-xs font-medium text-accent hover:underline">
        ← Back to Complaints
      </Link>

      <div
        className={`mt-4 flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4 ${
          flashKey === "status" ? "cs-admin-flash" : ""
        } ${shakeHeader ? "cs-admin-shake" : ""}`}
      >
        <div className="min-w-0">
          <h1 className="break-words text-xl font-semibold text-text">{data.subject}</h1>
          <p className="mt-1 break-words text-xs text-text-muted">
            {data.user_name} (
            <a href={`mailto:${data.user_email}`} className="text-accent hover:underline">
              {data.user_email}
            </a>
            ) · {formatComplaintCategory(data.category)} · {formatDateTime(data.created_at)}
          </p>
          {data.document_id && (
            <p className="mt-2 text-xs text-text-muted">
              Related document ID: <span className="font-mono text-text">{data.document_id}</span>{" "}
              (Admins cannot open documents)
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <SimpleStatusBadge status={data.status} kind="complaint" pop={flashKey === "status"} />
          <select
            aria-label="Update complaint status"
            value=""
            disabled={statusMutation.isPending}
            onChange={(e) => {
              const val = e.target.value as ComplaintStatus;
              if (val) statusMutation.mutate(val);
            }}
            className="h-8 rounded border border-border bg-bg px-2 text-xs text-text"
          >
            <option value="">Change status…</option>
            {nextStatuses.map((st) => (
              <option key={st} value={st}>
                {st === "in_progress"
                  ? data.status === "resolved"
                    ? "Reopen (In progress)"
                    : "In progress"
                  : "Resolved"}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Thread */}
      <div className="mt-6 divide-y divide-border border-b border-border">
        <div className="py-4">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="font-medium text-text">{data.user_name}</span>
            <span>{formatDateTime(data.created_at)}</span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-text">{data.message}</p>
        </div>

        {data.messages.map((msg) => (
          <div
            key={msg.id}
            className={`py-4 ${flashKey === msg.id ? "cs-admin-flash" : ""}`}
          >
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span className="font-medium text-text">
                {msg.author_name} ({msg.author_role})
              </span>
              <span>{formatDateTime(msg.created_at)}</span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm text-text">{msg.body}</p>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!replyBody.trim()) {
            setReplyError("Enter a reply.");
            return;
          }
          replyMutation.mutate(replyBody.trim());
        }}
        className="mt-6 space-y-3"
      >
        <Textarea
          id="admin-reply-body"
          label="Admin reply"
          value={replyBody}
          onChange={(e) => {
            setReplyBody(e.target.value);
            if (replyError) setReplyError(null);
          }}
          error={replyError || undefined}
        />
        <Button type="submit" loading={replyMutation.isPending}>
          Send reply
        </Button>
      </form>
    </div>
  );
}

export default function AdminComplaintDetailPage() {
  return (
    <AppLayout allowedRoles={["admin"]}>
      <AdminComplaintDetailContent />
    </AppLayout>
  );
}
