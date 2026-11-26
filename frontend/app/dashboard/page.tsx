"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { AppLayout } from "@/components/layout/AppLayout";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { DocumentStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatTaskType } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";

function DashboardContent() {
  const { user } = useAuth();
  const isRestricted = user?.status === "restricted";
  const firstName = user?.full_name.split(" ")[0] || "Doctor";

  const { data, isLoading, isError, refetch } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => apiRequest<DashboardResponse>("/dashboard"),
  });

  return (
    <div>
      {isRestricted && (
        <div
          role="alert"
          className="mb-6 rounded bg-danger-tint px-4 py-3 text-sm text-danger"
        >
          Your account is restricted. You can contact support from{" "}
          <Link href="/help" className="font-medium underline">
            Help
          </Link>
          .
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[28px] font-semibold text-text">Welcome, {firstName}</h1>
        {isRestricted ? (
          <button
            type="button"
            disabled
            className="inline-flex h-10 cursor-not-allowed items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white opacity-50"
          >
            New document
          </button>
        ) : (
          <Link
            href="/documents/new"
            className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
          >
            New document
          </Link>
        )}
      </div>

      {/* Plain row of three figures (no card grid, design.md §5) */}
      <dl className="mt-8 grid grid-cols-1 gap-6 border-y border-border py-6 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-text-muted">Processed this week</dt>
          <dd className="mt-1 text-2xl font-semibold text-text">
            {isLoading ? "—" : (data?.processed_last_7_days ?? 0)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-muted">Waiting for review</dt>
          <dd className="mt-1 text-2xl font-semibold text-text">
            {isLoading ? "—" : (data?.waiting_for_review ?? 0)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-muted">Blocked</dt>
          <dd className="mt-1 text-2xl font-semibold text-text">
            {isLoading ? "—" : (data?.blocked_count ?? 0)}
          </dd>
        </div>
      </dl>

      <section className="mt-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-text">Recent documents</h2>
          <Link href="/documents" className="text-sm font-medium text-accent hover:underline">
            View all
          </Link>
        </div>

        {isLoading ? (
          <TableSkeleton rows={5} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load dashboard data.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !data || data.recent_documents.length === 0 ? (
          <EmptyState
            message="No documents yet. Upload a PDF to begin."
            actionLabel={isRestricted ? undefined : "New document"}
            actionHref={isRestricted ? undefined : "/documents/new"}
          />
        ) : (
          <div className="overflow-x-auto">
            <table aria-label="Recent documents" className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-y border-border bg-bg-subtle text-xs font-medium text-text-muted">
                  <th className="px-3 py-2.5">Document</th>
                  <th className="px-3 py-2.5">Task</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.recent_documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-bg-subtle">
                    <td className="px-3 py-3 font-medium text-text">
                      <Link href={`/documents/${doc.id}`} className="hover:text-accent hover:underline">
                        {doc.original_filename}
                      </Link>
                    </td>
                    <td className="px-3 py-3 text-text-muted">{formatTaskType(doc.task_type)}</td>
                    <td className="px-3 py-3">
                      <DocumentStatusBadge status={doc.status} />
                    </td>
                    <td className="px-3 py-3 text-text-muted">{formatDateTime(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AppLayout allowedRoles={["doctor"]}>
      <DashboardContent />
    </AppLayout>
  );
}
