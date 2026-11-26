"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppLayout } from "@/components/layout/AppLayout";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Textarea } from "@/components/ui/FormFields";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { SimpleStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest, emitToast } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import type { AdminUserItem, AdminUserListResponse } from "@/lib/types";

function AdminUsersContent() {
  const { user: currentAdmin } = useAuth();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const initialStatus = searchParams.get("status") || "";

  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState(
    ["active", "restricted"].includes(initialStatus) ? initialStatus : "",
  );
  const [page, setPage] = useState(1);

  useEffect(() => {
    const paramStatus = searchParams.get("status") || "";
    if (["active", "restricted", ""].includes(paramStatus)) {
      setStatus(paramStatus);
      setPage(1);
    }
  }, [searchParams]);

  const [restrictTarget, setRestrictTarget] = useState<AdminUserItem | null>(null);
  const [restrictReason, setRestrictReason] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<AdminUserItem | null>(null);

  const [flashedId, setFlashedId] = useState<string | null>(null);
  const [shakenId, setShakenId] = useState<string | null>(null);

  const triggerFlash = (id: string) => {
    setFlashedId(id);
    setTimeout(() => setFlashedId((prev) => (prev === id ? null : prev)), 1300);
  };

  const triggerShake = (id: string) => {
    setShakenId(id);
    setTimeout(() => setShakenId((prev) => (prev === id ? null : prev)), 400);
  };

  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (role) params.set("role", role);
  if (status) params.set("status", status);
  params.set("page", String(page));
  params.set("page_size", "10");

  const { data, isLoading, isError, refetch } = useQuery<AdminUserListResponse>({
    queryKey: ["admin", "users", params.toString()],
    queryFn: () => apiRequest<AdminUserListResponse>(`/admin/users?${params.toString()}`),
  });

  const updateUserMutation = useMutation({
    mutationFn: (payload: {
      userId: string;
      body: { status?: "active" | "restricted"; restricted_reason?: string; role?: "doctor" | "auditor" };
      successMessage: string;
    }) =>
      apiRequest<AdminUserItem>(`/admin/users/${payload.userId}`, {
        method: "PATCH",
        body: payload.body,
      }),
    onSuccess: (_updated, variables) => {
      setRestrictTarget(null);
      setRestrictReason("");
      setRestoreTarget(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "overview"] });
      triggerFlash(variables.userId);
      emitToast({ kind: "success", message: variables.successMessage });
    },
    onError: (_err, variables) => {
      triggerShake(variables.userId);
    },
  });

  return (
    <div>
      <h1 className="text-[28px] font-semibold text-text">Users</h1>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input
          type="search"
          aria-label="Search users"
          placeholder="Search name or email"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text placeholder:text-text-muted"
        />

        <select
          aria-label="Filter by role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded border border-border bg-bg px-3 text-sm text-text"
        >
          <option value="">All roles</option>
          <option value="doctor">Doctor</option>
          <option value="auditor">Auditor</option>
          <option value="admin">Admin</option>
        </select>

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
          <option value="active">Active</option>
          <option value="restricted">Restricted</option>
        </select>
      </div>

      <div className="mt-6">
        {isLoading ? (
          <TableSkeleton rows={6} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load users.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No users match your filters." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table aria-label="Users" className="w-full border-collapse text-left text-sm">
                <thead className="bg-bg-subtle">
                  <tr className="border-y border-border text-xs font-medium text-text-muted">
                    <th className="px-3 py-2.5">Name</th>
                    <th className="px-3 py-2.5">Email</th>
                    <th className="px-3 py-2.5">Role</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5">Last login</th>
                    <th className="px-3 py-2.5">Documents</th>
                    <th className="px-3 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((u) => {
                    const isLockedRow = u.id === currentAdmin?.id || u.role === "admin";
                    const isFlashed = flashedId === u.id;
                    const isShaken = shakenId === u.id;
                    return (
                      <tr
                        key={u.id}
                        className={`hover:bg-bg-subtle ${isFlashed ? "cs-admin-flash" : ""} ${
                          isShaken ? "cs-admin-shake" : ""
                        }`}
                      >
                        <td className="px-3 py-3 font-medium text-text">{u.full_name}</td>
                        <td className="px-3 py-3 text-text-muted">
                          <a href={`mailto:${u.email}`} className="text-accent hover:underline">
                            {u.email}
                          </a>
                        </td>
                        <td className="px-3 py-3 capitalize text-text">
                          {isLockedRow ? (
                            u.role
                          ) : (
                            <select
                              aria-label={`Change role for ${u.full_name}`}
                              value={u.role}
                              disabled={updateUserMutation.isPending}
                              onChange={(e) =>
                                updateUserMutation.mutate({
                                  userId: u.id,
                                  body: { role: e.target.value as "doctor" | "auditor" },
                                  successMessage: "User role updated.",
                                })
                              }
                              className="h-8 rounded border border-border bg-bg px-2 text-xs text-text"
                            >
                              <option value="doctor">Doctor</option>
                              <option value="auditor">Auditor</option>
                            </select>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <SimpleStatusBadge status={u.status} kind="user" pop={isFlashed} />
                        </td>
                        <td className="px-3 py-3 text-text-muted">{formatDateTime(u.last_login_at)}</td>
                        <td className="px-3 py-3 text-text-muted">{u.documents_count}</td>
                        <td className="px-3 py-3 text-right">
                          {isLockedRow ? (
                            <span className="text-xs text-text-muted">—</span>
                          ) : u.status === "active" ? (
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => {
                                setRestrictTarget(u);
                                setRestrictReason("");
                              }}
                            >
                              Restrict
                            </Button>
                          ) : (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => setRestoreTarget(u)}
                            >
                              Restore
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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

      {/* Restrict modal with reason */}
      <Modal
        open={Boolean(restrictTarget)}
        title={`Restrict ${restrictTarget?.full_name || "user"}`}
        onClose={() => setRestrictTarget(null)}
      >
        <p className="text-sm text-text-muted">
          Restricting this user wipes their temporary session vault and stops any in-progress
          documents. They will still be able to view Profile and Help.
        </p>
        <div className="mt-4">
          <Textarea
            id="restrict-reason"
            label="Reason"
            placeholder="Describe why this account is being restricted"
            value={restrictReason}
            onChange={(e) => setRestrictReason(e.target.value)}
          />
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setRestrictTarget(null)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            loading={updateUserMutation.isPending}
            onClick={() =>
              restrictTarget &&
              updateUserMutation.mutate({
                userId: restrictTarget.id,
                body: {
                  status: "restricted",
                  restricted_reason: restrictReason.trim() || "Restricted by administrator",
                },
                successMessage: "User restricted.",
              })
            }
          >
            Restrict user
          </Button>
        </div>
      </Modal>

      {/* Restore confirm dialog */}
      <ConfirmDialog
        open={Boolean(restoreTarget)}
        title={`Restore ${restoreTarget?.full_name || "user"}`}
        message="Restore active access for this user?"
        confirmLabel="Restore"
        loading={updateUserMutation.isPending}
        onCancel={() => setRestoreTarget(null)}
        onConfirm={() =>
          restoreTarget &&
          updateUserMutation.mutate({
            userId: restoreTarget.id,
            body: { status: "active" },
            successMessage: "User restored.",
          })
        }
      />
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <AppLayout allowedRoles={["admin"]}>
      <Suspense fallback={<BrandLoader label="Loading users…" />}>
        <AdminUsersContent />
      </Suspense>
    </AppLayout>
  );
}
