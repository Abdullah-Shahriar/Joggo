"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { SimpleStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest, emitToast } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditLogListResponse, AuditVerifyResponse } from "@/lib/types";

function AuditLogsContent() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResponse | null>(null);

  const params = new URLSearchParams();
  if (actor.trim()) params.set("actor", actor.trim());
  if (action.trim()) params.set("action", action.trim());
  if (outcome) params.set("outcome", outcome);
  if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00Z`);
  if (dateTo) params.set("date_to", `${dateTo}T23:59:59Z`);
  params.set("page", String(page));
  params.set("page_size", "20");

  const { data, isLoading, isError, refetch } = useQuery<AuditLogListResponse>({
    queryKey: ["audit", params.toString()],
    queryFn: () => apiRequest<AuditLogListResponse>(`/audit?${params.toString()}`),
  });

  const verifyMutation = useMutation({
    mutationFn: () => apiRequest<AuditVerifyResponse>("/audit/verify"),
    onSuccess: (res) => {
      setVerifyResult(res);
      emitToast({
        kind: res.ok ? "success" : "error",
        message: res.ok
          ? `Audit chain verified (${res.checked} entries intact).`
          : `Integrity check failed at entry #${res.first_broken_id}.`,
      });
    },
  });

  const blockAuditCopy = (e: React.SyntheticEvent) => {
    e.preventDefault();
    emitToast({
      kind: "error",
      message: "Copying is disabled on protected security audit logs.",
    });
  };

  return (
    <div
      className="cs-no-copy"
      onCopy={blockAuditCopy}
      onCut={blockAuditCopy}
      onContextMenu={blockAuditCopy}
      onDragStart={(e) => e.preventDefault()}
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-[28px] font-semibold text-text">Audit logs</h1>
          <span className="inline-flex items-center gap-1 rounded border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            <Lock className="h-3 w-3 text-accent" aria-hidden="true" />
            Non-copyable
          </span>
        </div>
        <Button
          variant="secondary"
          loading={verifyMutation.isPending}
          onClick={() => verifyMutation.mutate()}
        >
          <ShieldCheck className="h-4 w-4 text-accent" />
          Verify log integrity
        </Button>
      </div>

      {verifyResult && (
        <div
          role="status"
          aria-live="polite"
          className={`mt-4 rounded px-4 py-3 text-sm ${
            verifyResult.ok
              ? "bg-accent-tint text-accent"
              : "bg-danger-tint text-danger"
          }`}
        >
          {verifyResult.ok
            ? `Hash chain verified. ${verifyResult.checked} entries checked with zero tampering.`
            : `Integrity check failed at entry #${verifyResult.first_broken_id} (${verifyResult.checked} checked).`}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <input
          type="text"
          aria-label="Filter by actor"
          placeholder="Actor role or UUID"
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text placeholder:text-text-muted"
        />

        <input
          type="text"
          aria-label="Filter by action"
          placeholder="Action (e.g. DOC_UPLOAD)"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text placeholder:text-text-muted"
        />

        <select
          aria-label="Filter by outcome"
          value={outcome}
          onChange={(e) => {
            setOutcome(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">All outcomes</option>
          <option value="allowed">Allowed</option>
          <option value="denied">Denied</option>
          <option value="error">Error</option>
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
          <TableSkeleton rows={8} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load audit logs.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No audit entries match your filters." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table aria-label="Audit logs" className="w-full border-collapse text-left text-sm">
                <thead className="bg-bg-subtle">
                  <tr className="border-y border-border text-xs font-medium text-text-muted">
                    <th className="px-3 py-2.5">Time</th>
                    <th className="px-3 py-2.5">Actor</th>
                    <th className="px-3 py-2.5">Action</th>
                    <th className="px-3 py-2.5">Resource</th>
                    <th className="px-3 py-2.5">Outcome</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((row) => (
                    <tr key={row.id} className="hover:bg-bg-subtle">
                      <td className="whitespace-nowrap px-3 py-2.5 text-text-muted">
                        {formatDateTime(row.ts)}
                      </td>
                      <td className="px-3 py-2.5 text-text">
                        <span className="capitalize">{row.actor_role || "system"}</span>
                        {row.actor_id && (
                          <span className="ml-1.5 font-mono text-xs text-text-muted">
                            {row.actor_id.slice(0, 8)}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-text">{row.action}</td>
                      <td className="px-3 py-2.5 text-xs text-text-muted">
                        {row.resource_type || "—"}
                        {row.resource_id ? ` · ${row.resource_id.slice(0, 8)}` : ""}
                      </td>
                      <td className="px-3 py-2.5">
                        <SimpleStatusBadge status={row.outcome} kind="outcome" />
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
    </div>
  );
}

export default function AdminAuditPage() {
  return (
    <AppLayout allowedRoles={["admin", "auditor"]}>
      <AuditLogsContent />
    </AppLayout>
  );
}
