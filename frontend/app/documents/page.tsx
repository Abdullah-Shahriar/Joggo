"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest, emitToast } from "@/lib/api";
import { formatDateTime, formatTaskType } from "@/lib/format";
import type { DocumentListResponse } from "@/lib/types";

type SortKey = "created_at" | "original_filename" | "status" | "entity_count";

function DocumentsListContent() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [taskType, setTaskType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sort, setSort] = useState<SortKey>("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (status) params.set("status", status);
  if (taskType) params.set("task_type", taskType);
  if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00Z`);
  if (dateTo) params.set("date_to", `${dateTo}T23:59:59Z`);
  params.set("sort", sort);
  params.set("order", order);
  params.set("page", String(page));
  params.set("page_size", "10");

  const { data, isLoading, isError, refetch } = useQuery<DocumentListResponse>({
    queryKey: ["documents", params.toString()],
    queryFn: () => apiRequest<DocumentListResponse>(`/documents?${params.toString()}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiRequest(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      emitToast({ kind: "success", message: "Document deleted." });
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: () => {
      setDeleteTarget(null);
    },
  });

  const toggleSort = (col: SortKey) => {
    if (sort === col) {
      setOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSort(col);
      setOrder("desc");
    }
    setPage(1);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[28px] font-semibold text-text">My documents</h1>
        <Link
          href="/documents/new"
          className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
        >
          New document
        </Link>
      </div>

      {/* Filters bar */}
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <input
          type="search"
          aria-label="Search documents"
          placeholder="Search filename or ID"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text placeholder:text-text-muted"
        />

        <select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">All statuses</option>
          <option value="UPLOADED">Uploaded</option>
          <option value="PROCESSING">Processing</option>
          <option value="BLOCKED">Blocked</option>
          <option value="REVIEW_REQUIRED">Review required</option>
          <option value="APPROVED">Approved</option>
          <option value="SENDING">Generating</option>
          <option value="COMPLETED">Completed</option>
          <option value="LLM_FAILED">Generation failed</option>
          <option value="FAILED">Failed</option>
        </select>

        <select
          aria-label="Filter by task"
          value={taskType}
          onChange={(e) => {
            setTaskType(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">All tasks</option>
          <option value="discharge_summary">Discharge summary</option>
          <option value="case_summary">Case summary</option>
          <option value="treatment_plan">Treatment plan</option>
        </select>

        <input
          type="date"
          aria-label="From date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        />

        <input
          type="date"
          aria-label="To date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        />
      </div>

      <div className="mt-6">
        {isLoading ? (
          <TableSkeleton rows={6} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load documents.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            message="No documents match your filters."
            actionLabel="Upload a document or photo"
            actionHref="/documents/new"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table aria-label="My documents" className="w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 bg-bg-subtle">
                  <tr className="border-y border-border text-xs font-medium text-text-muted">
                    <th className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => toggleSort("original_filename")}
                        className="inline-flex items-center gap-1 hover:text-text"
                      >
                        Document <ArrowUpDown className="h-3 w-3" />
                      </button>
                    </th>
                    <th className="px-3 py-2.5">Task</th>
                    <th className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => toggleSort("status")}
                        className="inline-flex items-center gap-1 hover:text-text"
                      >
                        Status <ArrowUpDown className="h-3 w-3" />
                      </button>
                    </th>
                    <th className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => toggleSort("entity_count")}
                        className="inline-flex items-center gap-1 hover:text-text"
                      >
                        Hidden details <ArrowUpDown className="h-3 w-3" />
                      </button>
                    </th>
                    <th className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => toggleSort("created_at")}
                        className="inline-flex items-center gap-1 hover:text-text"
                      >
                        Created <ArrowUpDown className="h-3 w-3" />
                      </button>
                    </th>
                    <th className="px-3 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => router.push(`/documents/${doc.id}`)}
                      className="cursor-pointer hover:bg-bg-subtle"
                    >
                      <td className="px-3 py-3 font-medium text-text">{doc.original_filename}</td>
                      <td className="px-3 py-3 text-text-muted">{formatTaskType(doc.task_type)}</td>
                      <td className="px-3 py-3">
                        <DocumentStatusBadge status={doc.status} />
                      </td>
                      <td className="px-3 py-3 text-text-muted">{doc.entity_count}</td>
                      <td className="px-3 py-3 text-text-muted">{formatDateTime(doc.created_at)}</td>
                      <td
                        className="px-3 py-3 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Button
                          variant="destructive"
                          size="sm"
                          title={`Delete ${doc.original_filename}`}
                          aria-label={`Delete ${doc.original_filename}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget({ id: doc.id, name: doc.original_filename });
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          <span>Delete</span>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onPageChange={setPage}
            />
          </>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete document"
        message={`Permanently delete "${deleteTarget?.name || ""}" and remove its temporary session data?`}
        confirmLabel="Delete"
        destructive
        loading={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
      />
    </div>
  );
}

export default function DocumentsListPage() {
  return (
    <AppLayout allowedRoles={["doctor"]}>
      <DocumentsListContent />
    </AppLayout>
  );
}
