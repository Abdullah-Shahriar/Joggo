"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { AppLayout } from "@/components/layout/AppLayout";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { apiRequest } from "@/lib/api";
import type { AdminOverviewResponse } from "@/lib/types";

function AdminOverviewContent() {
  const { data, isLoading, isError, refetch } = useQuery<AdminOverviewResponse>({
    queryKey: ["admin", "overview"],
    queryFn: () => apiRequest<AdminOverviewResponse>("/admin/overview"),
  });

  return (
    <div className="max-w-prose">
      <h1 className="text-[28px] font-semibold text-text">Overview</h1>
      <p className="mt-1 text-sm text-text-muted">
        Aggregate activity counts only. Clinical documents are never accessible to administrators.
      </p>

      {isLoading ? (
        <div className="mt-8">
          <TableSkeleton rows={4} />
        </div>
      ) : isError || !data ? (
        <div className="mt-8 rounded bg-danger-tint p-4 text-sm text-danger">
          Could not load overview counts.{" "}
          <button type="button" onClick={() => refetch()} className="font-medium underline">
            Try again
          </button>
        </div>
      ) : (
        <dl className="mt-8 divide-y divide-border border-y border-border">
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm text-text-muted">Open complaints</dt>
            <dd className="flex items-center gap-4">
              <span className="text-lg font-semibold text-text">{data.open_complaints}</span>
              <Link href="/admin/complaints?status=open" className="text-xs text-accent hover:underline">
                View
              </Link>
            </dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm text-text-muted">In progress</dt>
            <dd className="flex items-center gap-4">
              <span className="text-lg font-semibold text-text">{data.in_progress_complaints}</span>
              <Link
                href="/admin/complaints?status=in_progress"
                className="text-xs text-accent hover:underline"
              >
                View
              </Link>
            </dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm text-text-muted">Restricted users</dt>
            <dd className="flex items-center gap-4">
              <span className="text-lg font-semibold text-text">{data.restricted_users}</span>
              <Link href="/admin/users?status=restricted" className="text-xs text-accent hover:underline">
                View
              </Link>
            </dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm text-text-muted">Documents processed today</dt>
            <dd className="text-lg font-semibold text-text">{data.documents_processed_today}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

export default function AdminOverviewPage() {
  return (
    <AppLayout allowedRoles={["admin"]}>
      <AdminOverviewContent />
    </AppLayout>
  );
}
