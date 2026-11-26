"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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

const profileSchema = z.object({
  full_name: z.string().trim().min(2, "Name must be 2–80 characters.").max(80),
  age: z
    .string()
    .trim()
    .refine(
      (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 18 && Number(v) <= 120),
      "Enter an age between 18 and 120.",
    ),
  designation: z.string().trim().max(120, "Maximum 120 characters."),
  hospital_name: z.string().trim().max(160, "Maximum 160 characters."),
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

async function resizeImageToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read image file."));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Invalid image file."));
      img.onload = () => {
        const size = 256;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Canvas unavailable."));
          return;
        }
        const minSide = Math.min(img.width, img.height);
        const sx = (img.width - minSide) / 2;
        const sy = (img.height - minSide) / 2;
        ctx.drawImage(img, sx, sy, minSide, minSide, 0, 0, size, size);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
        resolve(dataUrl);
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

function ProfileContent() {
  const { user, setUser } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const avatarInputRef = useRef<HTMLInputElement>(null);

  const [confirmOthers, setConfirmOthers] = useState(false);
  const [avatarDraft, setAvatarDraft] = useState<string | null>(user?.avatar_data_url ?? null);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  const profileForm = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      full_name: user?.full_name || "",
      age: user?.age !== null && user?.age !== undefined ? String(user.age) : "",
      designation: user?.designation || "",
      hospital_name: user?.hospital_name || "",
    },
  });

  useEffect(() => {
    if (user) {
      profileForm.reset({
        full_name: user.full_name,
        age: user.age !== null && user.age !== undefined ? String(user.age) : "",
        designation: user.designation || "",
        hospital_name: user.hospital_name || "",
      });
      setAvatarDraft(user.avatar_data_url ?? null);
    }
  }, [user, profileForm]);

  const pwdForm = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
  });

  const { data: sessionsData, isLoading: sessionsLoading } = useQuery<{ items: SessionInfo[] }>({
    queryKey: ["me", "sessions"],
    queryFn: () => apiRequest<{ items: SessionInfo[] }>("/me/sessions"),
  });

  const updateProfileMutation = useMutation({
    mutationFn: (values: z.infer<typeof profileSchema>) =>
      apiRequest<AuthUser>("/me", {
        method: "PATCH",
        body: {
          full_name: values.full_name,
          age: values.age === "" ? null : Number(values.age),
          designation: values.designation,
          hospital_name: values.hospital_name,
          avatar_data_url: avatarDraft ?? "",
        },
      }),
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

  const handleAvatarChange = async (file: File | null) => {
    setAvatarError(null);
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setAvatarError("Choose a PNG, JPEG, or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setAvatarError("Image must be smaller than 5 MB.");
      return;
    }
    try {
      const resized = await resizeImageToDataUrl(file);
      setAvatarDraft(resized);
      emitToast({ kind: "success", message: "Photo ready — click Save changes to update." });
    } catch {
      setAvatarError("Could not process the selected image.");
    }
  };

  if (!user) return null;

  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const signInMethod =
    user.has_password && user.has_google
      ? "Email and Google"
      : user.has_google
        ? "Google"
        : "Email";

  const otherSessionsCount = (sessionsData?.items || []).filter((s) => !s.is_current).length;

  return (
    <div className="mx-auto max-w-form space-y-10">
      <div>
        <h1 className="text-[28px] font-semibold text-text">Profile</h1>
        <p className="mt-1 text-[15px] text-text-muted">
          Manage your clinician details, password, and active sessions.
        </p>
      </div>

      {user.status === "restricted" && (
        <div role="alert" className="rounded bg-danger-tint px-4 py-3 text-sm text-danger">
          Your account is restricted. You can contact support from{" "}
          <Link href="/help" className="font-medium underline">
            Help
          </Link>
          .
        </div>
      )}

      {/* Section 1: Account & Clinician Profile */}
      <section className="space-y-5">
        <h2 className="text-xl font-semibold text-text">Account</h2>

        {/* Profile picture picker */}
        <div className="flex flex-wrap items-center gap-4">
          {avatarDraft ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={avatarDraft}
              alt={`${user.full_name} profile picture`}
              className="h-16 w-16 rounded-full border border-border object-cover"
            />
          ) : (
            <div
              aria-hidden="true"
              className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-accent-tint text-lg font-semibold text-accent"
            >
              {initials}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => handleAvatarChange(e.target.files?.[0] || null)}
              className="sr-only"
              aria-label="Upload profile picture"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => avatarInputRef.current?.click()}
            >
              <Camera className="h-4 w-4" />
              {avatarDraft ? "Change photo" : "Upload photo"}
            </Button>
            {avatarDraft && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setAvatarDraft(null);
                  emitToast({ kind: "success", message: "Photo removed — click Save changes to apply." });
                }}
              >
                <Trash2 className="h-4 w-4 text-danger" />
                Remove
              </Button>
            )}
          </div>
          {avatarError && (
            <p role="alert" className="w-full text-xs text-danger">
              {avatarError}
            </p>
          )}
        </div>

        <form
          onSubmit={profileForm.handleSubmit((vals) => updateProfileMutation.mutate(vals))}
          className="space-y-4"
          noValidate
        >
          <Input
            id="profile-name"
            label="Full name"
            error={profileForm.formState.errors.full_name?.message}
            {...profileForm.register("full_name")}
          />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              id="profile-age"
              label="Age"
              type="number"
              min={18}
              max={120}
              placeholder="e.g. 36"
              error={profileForm.formState.errors.age?.message}
              {...profileForm.register("age")}
            />

            <Input
              id="profile-designation"
              label="Designation"
              type="text"
              placeholder="e.g. Consultant Physician"
              error={profileForm.formState.errors.designation?.message}
              {...profileForm.register("designation")}
            />
          </div>

          <Input
            id="profile-hospital"
            label="Hospital name"
            type="text"
            placeholder="e.g. City Care Medical College"
            error={profileForm.formState.errors.hospital_name?.message}
            {...profileForm.register("hospital_name")}
          />

          <Button type="submit" loading={updateProfileMutation.isPending}>
            Save changes
          </Button>
        </form>

        <dl className="grid grid-cols-1 gap-3 border-t border-border pt-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-text-muted">Email</dt>
            <dd className="break-all text-text">
              <a href={`mailto:${user.email}`} className="text-accent hover:underline">
                {user.email}
              </a>
            </dd>
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
          <p className="text-[15px] text-text-muted">
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
