"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { SimpleStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest } from "@/lib/api";
import { formatComplaintCategory, formatDateTime } from "@/lib/format";
import type { ComplaintListResponse } from "@/lib/types";

function AdminComplaintsContent() {
  const searchParams = useSearchParams();
  const initialStatus = searchParams.get("status") || "";
  const [status, setStatus] = useState(
    ["open", "in_progress", "resolved"].includes(initialStatus) ? initialStatus : "",
  );
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const paramStatus = searchParams.get("status") || "";
    if (["open", "in_progress", "resolved", ""].includes(paramStatus)) {
      setStatus(paramStatus);
      setPage(1);
    }
  }, [searchParams]);

  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  if (q.trim()) params.set("q", q.trim());
  params.set("page", String(page));
  params.set("page_size", "10");

  const { data, isLoading, isError, refetch } = useQuery<ComplaintListResponse>({
    queryKey: ["admin", "complaints", params.toString()],
    queryFn: () => apiRequest<ComplaintListResponse>(`/admin/complaints?${params.toString()}`),
  });

  return (
    <div>
      <h1 className="text-[28px] font-semibold text-text">Complaints</h1>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input
          type="search"
          aria-label="Search complaints"
          placeholder="Search subject or user"
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
          <option value="open">Open</option>
          <option value="in_progress">In progress</option>
          <option value="resolved">Resolved</option>
        </select>

        <select
          aria-label="Filter by category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">All categories</option>
          <option value="bug">Bug</option>
          <option value="account">Account</option>
          <option value="privacy">Privacy</option>
          <option value="other">Other</option>
        </select>
      </div>

      <div className="mt-6">
        {isLoading ? (
          <TableSkeleton rows={5} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load complaints.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No complaints found." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table aria-label="Complaints inbox" className="w-full border-collapse text-left text-sm">
                <thead className="bg-bg-subtle">
                  <tr className="border-y border-border text-xs font-medium text-text-muted">
                    <th className="px-3 py-2.5">Subject</th>
                    <th className="px-3 py-2.5">User</th>
                    <th className="px-3 py-2.5">Category</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((c) => (
                    <tr key={c.id} className="hover:bg-bg-subtle">
                      <td className="px-3 py-3 font-medium text-text">
                        <Link
                          href={`/admin/complaints/${c.id}`}
                          className="hover:text-accent hover:underline"
                        >
                          {c.subject}
                        </Link>
                      </td>
                      <td className="px-3 py-3 text-text-muted">{c.user_name}</td>
                      <td className="px-3 py-3 text-text-muted">
                        {formatComplaintCategory(c.category)}
                      </td>
                      <td className="px-3 py-3">
                        <SimpleStatusBadge status={c.status} kind="complaint" />
                      </td>
                      <td className="px-3 py-3 text-text-muted">{formatDateTime(c.updated_at)}</td>
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
    </div>
  );
}

export default function AdminComplaintsPage() {
  return (
    <AppLayout allowedRoles={["admin"]}>
      <Suspense fallback={<BrandLoader label="Loading complaints…" />}>
        <AdminComplaintsContent />
      </Suspense>
    </AppLayout>
  );
}
