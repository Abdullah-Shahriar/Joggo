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
import type { ComplaintDetail } from "@/lib/types";

function HelpDetailContent() {
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [replyBody, setReplyBody] = useState("");
  const [replyError, setReplyError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery<ComplaintDetail>({
    queryKey: ["complaint", params.id],
    queryFn: () => apiRequest<ComplaintDetail>(`/complaints/${params.id}`),
  });

  const replyMutation = useMutation({
    mutationFn: (body: string) =>
      apiRequest<ComplaintDetail>(`/complaints/${params.id}/messages`, {
        method: "POST",
        body: { body },
      }),
    onSuccess: (updated) => {
      setReplyBody("");
      setReplyError(null);
      queryClient.setQueryData(["complaint", params.id], updated);
      emitToast({ kind: "success", message: "Reply sent." });
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

  return (
    <div className="max-w-prose">
      <Link href="/help" className="text-xs font-medium text-accent hover:underline">
        ← Back to Help
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="min-w-0">
          <h1 className="break-words text-xl font-semibold text-text">{data.subject}</h1>
          <p className="mt-1 text-xs text-text-muted">
            {formatComplaintCategory(data.category)} · Filed {formatDateTime(data.created_at)}
          </p>
        </div>
        <SimpleStatusBadge status={data.status} kind="complaint" />
      </div>

      {/* Plain thread list */}
      <div className="mt-6 divide-y divide-border border-b border-border">
        <div className="py-4">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="font-medium text-text">{data.user_name}</span>
            <span>{formatDateTime(data.created_at)}</span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-text">{data.message}</p>
        </div>

        {data.messages.map((msg) => (
          <div key={msg.id} className="py-4">
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

      <div className="mt-6">
        {data.status === "resolved" ? (
          <p className="text-sm text-text-muted">This complaint is resolved.</p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!replyBody.trim()) {
                setReplyError("Enter a reply message.");
                return;
              }
              replyMutation.mutate(replyBody.trim());
            }}
            className="space-y-3"
          >
            <Textarea
              id="reply-body"
              label="Reply"
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
        )}
      </div>
    </div>
  );
}

export default function HelpDetailPage() {
  return (
    <AppLayout allowedRoles={["doctor", "auditor"]}>
      <HelpDetailContent />
    </AppLayout>
  );
}
