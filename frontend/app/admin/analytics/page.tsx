"use client";

import { useQuery } from "@tanstack/react-query";

import { AppLayout } from "@/components/layout/AppLayout";
import { ActivityHeatmap } from "@/components/ui/ActivityHeatmap";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { apiRequest } from "@/lib/api";
import type { AdminAnalyticsResponse } from "@/lib/types";

function BarRow({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.max(2, Math.round((count / max) * 100)) : 0;
  return (
    <tr className="border-b border-border">
      <td className="w-28 py-2 pr-3 text-xs capitalize text-text sm:w-40 sm:pr-4 sm:text-sm">
        {label}
      </td>
      <td className="py-2 pr-3 sm:pr-4">
        <div className="h-2.5 w-full rounded bg-bg-subtle">
          {count > 0 && <div className="h-2.5 rounded bg-accent" style={{ width: `${pct}%` }} />}
        </div>
      </td>
      <td className="w-12 py-2 text-right text-xs font-medium text-text sm:w-16 sm:text-sm">
        {count}
      </td>
    </tr>
  );
}

function AdminActivityBand() {
  const { data } = useQuery<AdminAnalyticsResponse>({
    queryKey: ["admin", "analytics"],
    queryFn: () => apiRequest<AdminAnalyticsResponse>("/admin/analytics"),
  });

  if (!data?.activity_heatmap) return null;

  return (
    <ActivityHeatmap
      fullWidth
      data={data.activity_heatmap}
      title="Platform activity"
      subtitle="Daily uploads, reviews, written drafts, and support activity across the last 13 weeks."
    />
  );
}

function AdminAnalyticsContent() {
  const { data, isLoading, isError, refetch } = useQuery<AdminAnalyticsResponse>({
    queryKey: ["admin", "analytics"],
    queryFn: () => apiRequest<AdminAnalyticsResponse>("/admin/analytics"),
  });

  if (isLoading) {
    return (
      <div>
        <h1 className="text-[28px] font-semibold text-text">Analytics</h1>
        <div className="mt-8">
          <TableSkeleton rows={6} />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded bg-danger-tint p-4 text-sm text-danger">
        Could not load analytics.{" "}
        <button type="button" onClick={() => refetch()} className="font-medium underline">
          Try again
        </button>
      </div>
    );
  }

  const maxDay = Math.max(1, ...data.documents_per_day.map((d) => d.total));
  const maxEntity = Math.max(1, ...data.entity_type_totals.map((e) => e.count));
  const maxRole = Math.max(1, ...Object.values(data.users_by_role));
  const maxProvider = Math.max(1, ...Object.values(data.llm_provider_usage), 1);

  return (
    <div className="space-y-12">
      <div>
        <h1 className="text-[28px] font-semibold text-text">Analytics</h1>
        <p className="mt-1.5 text-[15px] text-text-muted">
          General usage numbers only. Document contents and filenames are never shown to
          administrators.
        </p>
      </div>

      {/* Headline metrics row */}
      <dl className="grid grid-cols-1 gap-6 border-y border-border py-5 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-text-muted">Safety hold rate</dt>
          <dd className="mt-1 text-xl font-semibold text-text">
            {(data.safety_block_rate * 100).toFixed(1)}%
          </dd>
        </div>
        <div>
          <dt className="text-xs text-text-muted">Backup AI switches</dt>
          <dd className="mt-1 text-xl font-semibold text-text">{data.llm_fallback_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-text-muted">Average AI response time</dt>
          <dd className="mt-1 text-xl font-semibold text-text">
            {data.avg_llm_latency_ms !== null ? `${Math.round(data.avg_llm_latency_ms)} ms` : "—"}
          </dd>
        </div>
      </dl>

      {/* Users by role & status */}
      <section className="grid grid-cols-1 gap-10 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-text">Users by role</h2>
          <table aria-label="Users by role" className="w-full border-collapse">
            <tbody>
              {Object.entries(data.users_by_role).map(([role, count]) => (
                <BarRow key={role} label={role} count={count} max={maxRole} />
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h2 className="mb-3 text-lg font-semibold text-text">Users by status</h2>
          <table aria-label="Users by status" className="w-full border-collapse">
            <tbody>
              {Object.entries(data.users_by_status).map(([st, count]) => (
                <BarRow key={st} label={st} count={count} max={maxRole} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Documents per day (14 days) */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-text">Documents per day (last 14 days)</h2>
        <table aria-label="Documents per day" className="w-full border-collapse">
          <tbody>
            {data.documents_per_day.map((row) => (
              <BarRow key={row.date} label={row.date} count={row.total} max={maxDay} />
            ))}
          </tbody>
        </table>
      </section>

      {/* AI providers & Complaints */}
      <section className="grid grid-cols-1 gap-10 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold text-text">AI writing service usage</h2>
          {Object.keys(data.llm_provider_usage).length === 0 ? (
            <p className="text-sm text-text-muted">No completed drafts yet.</p>
          ) : (
            <table aria-label="AI writing service usage" className="w-full border-collapse">
              <tbody>
                {Object.entries(data.llm_provider_usage).map(([prov, count]) => (
                  <BarRow key={prov} label={prov} count={count} max={maxProvider} />
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div>
          <h2 className="mb-3 text-lg font-semibold text-text">Support tickets by status</h2>
          {Object.keys(data.complaints_by_status).length === 0 ? (
            <p className="text-sm text-text-muted">No support tickets recorded.</p>
          ) : (
            <table aria-label="Support tickets by status" className="w-full border-collapse">
              <tbody>
                {Object.entries(data.complaints_by_status).map(([st, count]) => (
                  <BarRow
                    key={st}
                    label={st.replace("_", " ")}
                    count={count}
                    max={Math.max(1, ...Object.values(data.complaints_by_status))}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Hidden details totals */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-text">Hidden detail categories</h2>
        {data.entity_type_totals.length === 0 ? (
          <p className="text-sm text-text-muted">No hidden personal details recorded yet.</p>
        ) : (
          <table aria-label="Hidden detail categories" className="w-full border-collapse">
            <tbody>
              {data.entity_type_totals.map((row) => (
                <BarRow key={row.entity_type} label={row.entity_type} count={row.count} max={maxEntity} />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

export default function AdminAnalyticsPage() {
  return (
    <AppLayout allowedRoles={["admin"]} preFooter={<AdminActivityBand />}>
      <AdminAnalyticsContent />
    </AppLayout>
  );
}
