"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/FormFields";
import { ConfirmDialog } from "@/components/ui/Modal";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { apiRequest, emitToast } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateOnly, formatDateTime } from "@/lib/format";
import type { AuthUser, SessionInfo } from "@/lib/types";

const nameSchema = z.object({
  full_name: z.string().trim().min(2, "Name must be 2–80 characters.").max(80),
});

const passwordSchema = z
  .object({
    current: z.string().min(1, "Enter your current password."),
    new: z
      .string()
      .min(10, "Password must be at least 10 characters.")
      .refine((v) => /[A-Za-z]/.test(v), "Include at least one letter.")
      .refine((v) => /\d/.test(v), "Include at least one digit."),
    confirm: z.string().min(1, "Confirm your new password."),
  })
  .refine((v) => v.new === v.confirm, {
    message: "Passwords do not match.",
    path: ["confirm"],
  });

function ProfileContent() {
  const { user, setUser } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirmOthers, setConfirmOthers] = useState(false);

  const nameForm = useForm<z.infer<typeof nameSchema>>({
    resolver: zodResolver(nameSchema),
    defaultValues: { full_name: user?.full_name || "" },
  });

  useEffect(() => {
    if (user) {
      nameForm.reset({ full_name: user.full_name });
    }
  }, [user, nameForm]);

  const pwdForm = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
  });

  const { data: sessionsData, isLoading: sessionsLoading } = useQuery<{ items: SessionInfo[] }>({
    queryKey: ["me", "sessions"],
    queryFn: () => apiRequest<{ items: SessionInfo[] }>("/me/sessions"),
  });

  const updateNameMutation = useMutation({
    mutationFn: (values: z.infer<typeof nameSchema>) =>
      apiRequest<AuthUser>("/me", { method: "PATCH", body: values }),
    onSuccess: (updated) => {
      setUser(updated);
      emitToast({ kind: "success", message: "Profile updated." });
    },
  });

  const updatePasswordMutation = useMutation({
    mutationFn: (values: z.infer<typeof passwordSchema>) =>
      apiRequest("/me/password", {
        method: "POST",
        body: { current: values.current, new: values.new },
      }),
    onSuccess: () => {
      emitToast({ kind: "success", message: "Password updated. Sign in again." });
      setUser(null);
      router.replace("/login");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => apiRequest(`/me/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      emitToast({ kind: "success", message: "Session signed out." });
      queryClient.invalidateQueries({ queryKey: ["me", "sessions"] });
    },
  });

  const revokeOthersMutation = useMutation({
    mutationFn: async () => {
      const others = (sessionsData?.items || []).filter((s) => !s.is_current);
      for (const sess of others) {
        await apiRequest(`/me/sessions/${sess.id}`, { method: "DELETE" });
      }
    },
    onSuccess: () => {
      setConfirmOthers(false);
      emitToast({ kind: "success", message: "Signed out all other devices." });
      queryClient.invalidateQueries({ queryKey: ["me", "sessions"] });
    },
  });

  if (!user) return null;

  const signInMethod =
    user.has_password && user.has_google
      ? "Email and Google"
      : user.has_google
        ? "Google"
        : "Email";

  const otherSessionsCount = (sessionsData?.items || []).filter((s) => !s.is_current).length;

  return (
    <div className="mx-auto max-w-form space-y-10">
      <h1 className="text-[28px] font-semibold text-text">Profile</h1>

      {user.status === "restricted" && (
        <div role="alert" className="rounded bg-danger-tint px-4 py-3 text-sm text-danger">
          Your account is restricted. You can contact support from{" "}
          <Link href="/help" className="font-medium underline">
            Help
          </Link>
          .
        </div>
      )}

      {/* Section 1: Account */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-text">Account</h2>
        <form
          onSubmit={nameForm.handleSubmit((vals) => updateNameMutation.mutate(vals))}
          className="space-y-4"
          noValidate
        >
          <Input
            id="profile-name"
            label="Full name"
            error={nameForm.formState.errors.full_name?.message}
            {...nameForm.register("full_name")}
          />
          <Button type="submit" loading={updateNameMutation.isPending}>
            Save
          </Button>
        </form>

        <dl className="grid grid-cols-1 gap-3 pt-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-text-muted">Email</dt>
            <dd className="text-text">{user.email}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Role</dt>
            <dd className="capitalize text-text">{user.role}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Member since</dt>
            <dd className="text-text">{formatDateOnly(user.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Sign-in method</dt>
            <dd className="text-text">{signInMethod}</dd>
          </div>
        </dl>
      </section>

      {/* Section 2: Password */}
      <section className="space-y-4 border-t border-border pt-8">
        <h2 className="text-xl font-semibold text-text">Password</h2>
        {!user.has_password ? (
          <p className="text-sm text-text-muted">
            You sign in with Google, so there is no password to change.
          </p>
        ) : (
          <form
            onSubmit={pwdForm.handleSubmit((vals) => updatePasswordMutation.mutate(vals))}
            className="space-y-4"
            noValidate
          >
            <Input
              id="pwd-current"
              label="Current password"
              type="password"
              autoComplete="current-password"
              error={pwdForm.formState.errors.current?.message}
              {...pwdForm.register("current")}
            />
            <Input
              id="pwd-new"
              label="New password"
              type="password"
              autoComplete="new-password"
              error={pwdForm.formState.errors.new?.message}
              {...pwdForm.register("new")}
            />
            <Input
              id="pwd-confirm"
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              error={pwdForm.formState.errors.confirm?.message}
              {...pwdForm.register("confirm")}
            />
            <Button type="submit" loading={updatePasswordMutation.isPending}>
              Update password
            </Button>
          </form>
        )}
      </section>

      {/* Section 3: Active sessions */}
      <section className="space-y-4 border-t border-border pt-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-semibold text-text">Active sessions</h2>
          {otherSessionsCount > 0 && (
            <Button variant="secondary" size="sm" onClick={() => setConfirmOthers(true)}>
              Sign out all other devices
            </Button>
          )}
        </div>

        {sessionsLoading ? (
          <TableSkeleton rows={2} />
        ) : (
          <div className="overflow-x-auto">
            <table aria-label="Active sessions" className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-y border-border bg-bg-subtle text-xs font-medium text-text-muted">
                  <th className="px-3 py-2">Device</th>
                  <th className="px-3 py-2">IP</th>
                  <th className="px-3 py-2">Last active</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(sessionsData?.items || []).map((sess) => (
                  <tr key={sess.id}>
                    <td className="max-w-[220px] truncate px-3 py-2.5 text-text">
                      {sess.user_agent || "Browser session"}
                      {sess.is_current && (
                        <span className="ml-2 rounded bg-accent-tint px-1.5 py-0.5 text-[11px] font-medium text-accent">
                          This device
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-text-muted">{sess.ip || "—"}</td>
                    <td className="px-3 py-2.5 text-text-muted">
                      {formatDateTime(sess.last_used_at || sess.created_at)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {!sess.is_current ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => revokeMutation.mutate(sess.id)}
                        >
                          Sign out
                        </Button>
                      ) : (
                        <span className="text-xs text-text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={confirmOthers}
        title="Sign out all other devices"
        message="This will end all other active sessions and wipe temporary session memory on those devices."
        confirmLabel="Sign out others"
        destructive
        loading={revokeOthersMutation.isPending}
        onCancel={() => setConfirmOthers(false)}
        onConfirm={() => revokeOthersMutation.mutate()}
      />
    </div>
  );
}

export default function ProfilePage() {
  return (
    <AppLayout>
      <ProfileContent />
    </AppLayout>
  );
}
