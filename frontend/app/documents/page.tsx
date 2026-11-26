"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, ClipboardList, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

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

const VALID_SORTS: ReadonlySet<SortKey> = new Set([
  "created_at",
  "original_filename",
  "status",
  "entity_count",
]);

const VALID_STATUSES: ReadonlySet<string> = new Set([
  "UPLOADED",
  "PROCESSING",
  "BLOCKED",
  "REVIEW_REQUIRED",
  "APPROVED",
  "SENDING",
  "COMPLETED",
  "LLM_FAILED",
  "FAILED",
]);

const VALID_TASKS: ReadonlySet<string> = new Set([
  "discharge_summary",
  "case_summary",
  "treatment_plan",
]);

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

interface FilterState {
  q: string;
  status: string;
  taskType: string;
  dateFrom: string;
  dateTo: string;
  sort: SortKey;
  order: "asc" | "desc";
  page: number;
}

function parseFiltersFromSearchParams(sp: URLSearchParams): FilterState {
  const rawQ = sp.get("q") || "";
  const rawStatus = sp.get("status") || "";
  const rawTask = sp.get("task_type") || "";
  const rawFrom = sp.get("date_from") || "";
  const rawTo = sp.get("date_to") || "";
  const rawSort = sp.get("sort") || "created_at";
  const rawOrder = sp.get("order") || "desc";
  const rawPage = Number.parseInt(sp.get("page") || "1", 10);

  return {
    q: rawQ,
    status: VALID_STATUSES.has(rawStatus) ? rawStatus : "",
    taskType: VALID_TASKS.has(rawTask) ? rawTask : "",
    dateFrom: DATE_RE.test(rawFrom) ? rawFrom : "",
    dateTo: DATE_RE.test(rawTo) ? rawTo : "",
    sort: VALID_SORTS.has(rawSort as SortKey) ? (rawSort as SortKey) : "created_at",
    order: rawOrder === "asc" ? "asc" : "desc",
    page: Number.isFinite(rawPage) && rawPage >= 1 ? rawPage : 1,
  };
}

function buildUrlQuery(next: FilterState): string {
  const out = new URLSearchParams();
  if (next.q.trim()) out.set("q", next.q.trim());
  if (next.status) out.set("status", next.status);
  if (next.taskType) out.set("task_type", next.taskType);
  if (next.dateFrom) out.set("date_from", next.dateFrom);
  if (next.dateTo) out.set("date_to", next.dateTo);
  if (next.sort !== "created_at") out.set("sort", next.sort);
  if (next.order !== "desc") out.set("order", next.order);
  if (next.page > 1) out.set("page", String(next.page));
  return out.toString();
}

function DocumentsListContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const filters = parseFiltersFromSearchParams(searchParams);
  const { q, status, taskType, dateFrom, dateTo, sort, order, page } = filters;

  const [searchInput, setSearchInput] = useState(q);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  // Restore search box value on initial load and browser back/forward navigation
  useEffect(() => {
    setSearchInput(q);
  }, [q]);

  const replaceFilters = useCallback(
    (patch: Partial<FilterState>) => {
      const next: FilterState = { ...filters, ...patch };
      const qs = buildUrlQuery(next);
      const currentQs = searchParams.toString();
      if (qs === currentQs) return;
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [filters, pathname, router, searchParams],
  );

  const hasActiveFilters = Boolean(q.trim() || status || taskType || dateFrom || dateTo);

  const clearFilters = useCallback(() => {
    setSearchInput("");
    const cleared: FilterState = {
      q: "",
      status: "",
      taskType: "",
      dateFrom: "",
      dateTo: "",
      sort: "created_at",
      order: "desc",
      page: 1,
    };
    const qs = buildUrlQuery(cleared);
    if (qs !== searchParams.toString()) {
      router.replace(pathname, { scroll: false });
    }
  }, [pathname, router, searchParams]);

  const apiParams = new URLSearchParams();
  if (q.trim()) apiParams.set("q", q.trim());
  if (status) apiParams.set("status", status);
  if (taskType) apiParams.set("task_type", taskType);
  if (dateFrom) apiParams.set("date_from", `${dateFrom}T00:00:00Z`);
  if (dateTo) apiParams.set("date_to", `${dateTo}T23:59:59Z`);
  apiParams.set("sort", sort);
  apiParams.set("order", order);
  apiParams.set("page", String(page));
  apiParams.set("page_size", "10");

  const { data, isLoading, isError, refetch } = useQuery<DocumentListResponse>({
    queryKey: ["documents", apiParams.toString()],
    queryFn: () => apiRequest<DocumentListResponse>(`/documents?${apiParams.toString()}`),
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
      replaceFilters({ order: order === "asc" ? "desc" : "asc", page: 1 });
    } else {
      replaceFilters({ sort: col, order: "desc", page: 1 });
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="flex items-center gap-2.5 text-[28px] font-semibold text-text">
          <ClipboardList className="h-6 w-6 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
          <span>My documents</span>
        </h1>
        <Link
          href="/documents/new"
          className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
        >
          New document
        </Link>
      </div>

      {/* Filters bar */}
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <input
            type="search"
            aria-label="Search documents"
            placeholder="Search filename or ID"
            value={searchInput}
            onChange={(e) => {
              const val = e.target.value;
              setSearchInput(val);
              replaceFilters({ q: val, page: 1 });
            }}
            className="h-10 rounded border border-border bg-bg px-3 text-sm text-text placeholder:text-text-muted"
          />

          <select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => replaceFilters({ status: e.target.value, page: 1 })}
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
            onChange={(e) => replaceFilters({ taskType: e.target.value, page: 1 })}
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
            onChange={(e) => replaceFilters({ dateFrom: e.target.value, page: 1 })}
            className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
          />

          <input
            type="date"
            aria-label="To date"
            value={dateTo}
            onChange={(e) => replaceFilters({ dateTo: e.target.value, page: 1 })}
            className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
          />
        </div>

        <Button
          variant="ghost"
          size="sm"
          disabled={!hasActiveFilters}
          onClick={clearFilters}
          className="self-start whitespace-nowrap lg:self-auto"
        >
          Clear filters
        </Button>
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
            secondaryActionLabel={hasActiveFilters ? "Clear filters" : undefined}
            onSecondaryAction={hasActiveFilters ? clearFilters : undefined}
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
                      <td className="px-3 py-3 font-medium text-text">
                        <div>{doc.original_filename}</div>
                        {doc.vault_expired && (
                          <p className="mt-0.5 text-xs font-normal text-text-muted">
                            The server restarted, so original details were cleared. Upload the file again.
                          </p>
                        )}
                      </td>
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
              onPageChange={(nextPage) => replaceFilters({ page: nextPage })}
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
      <Suspense fallback={<TableSkeleton rows={6} />}>
        <DocumentsListContent />
      </Suspense>
    </AppLayout>
  );
}
