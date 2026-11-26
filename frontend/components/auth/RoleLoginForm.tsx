"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Shield } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthSplitShell } from "@/components/auth/AuthSplitShell";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/FormFields";
import { ApiError, apiRequest, emitToast } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getRoleHome, type UserRole } from "@/lib/constants";
import type { AuthSessionResponse, AuthUser } from "@/lib/types";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

function isPathAllowedForRole(role: UserRole, pathOnly: string): boolean {
  if (pathOnly === "/profile" || pathOnly.startsWith("/profile/")) {
    return true;
  }
  if (role === "doctor") {
    return (
      pathOnly === "/dashboard" ||
      pathOnly === "/documents" ||
      pathOnly.startsWith("/documents/") ||
      pathOnly === "/help" ||
      pathOnly.startsWith("/help/")
    );
  }
  if (role === "admin") {
    return pathOnly === "/admin" || pathOnly.startsWith("/admin/");
  }
  // auditor
  return (
    pathOnly === "/admin/audit" ||
    pathOnly.startsWith("/admin/audit/") ||
    pathOnly === "/help" ||
    pathOnly.startsWith("/help/")
  );
}

function resolvePostLoginDestination(role: UserRole, nextParam: string | null): string {
  if (
    nextParam &&
    nextParam.startsWith("/") &&
    !nextParam.startsWith("//") &&
    !nextParam.startsWith("/\\")
  ) {
    const pathOnly = nextParam.split(/[?#]/, 1)[0];
    if (isPathAllowedForRole(role, pathOnly)) {
      return nextParam;
    }
  }
  return getRoleHome(role);
}

function RoleLoginInner({
  portal,
  title,
  subtitle,
  badge,
  showGoogle = false,
  showSignupLink = false,
}: {
  portal: UserRole;
  title: string;
  subtitle: string;
  badge?: string;
  showGoogle?: boolean;
  showSignupLink?: boolean;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isLoading, setUser } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const redirectAfterLogin = useCallback(
    (loggedInUser: AuthUser) => {
      const dest = resolvePostLoginDestination(loggedInUser.role, searchParams.get("next"));
      router.replace(dest);
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (!isLoading && user) {
      redirectAfterLogin(user);
    }
  }, [isLoading, user, redirectAfterLogin]);

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      const data = await apiRequest<AuthSessionResponse>("/auth/login", {
        method: "POST",
        body: { ...values, portal },
        silentErrorToast: true,
      });
      setUser(data.user);
      emitToast({ kind: "success", message: "Signed in successfully." });
      redirectAfterLogin(data.user);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Unable to sign in. Please try again.");
      }
    }
  };

  if (user) {
    return <BrandLoader fullScreen label="Redirecting…" />;
  }

  return (
    <AuthSplitShell>
      <div className="rounded border border-border bg-bg p-6 sm:p-8">
        {badge && (
          <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accent-tint px-2.5 py-0.5 text-xs font-semibold text-accent">
            <Shield className="h-3.5 w-3.5" aria-hidden="true" />
            {badge}
          </span>
        )}
        <h1 className="text-2xl font-semibold text-text">{title}</h1>
        <p className="mt-1.5 text-[15px] text-text-muted">{subtitle}</p>

        {formError && (
          <div role="alert" className="mt-4 rounded bg-danger-tint px-3.5 py-2.5 text-sm text-danger">
            {formError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <Input
            id={`${portal}-login-email`}
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />

          <div className="relative">
            <Input
              id={`${portal}-login-password`}
              label="Password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              className="pr-10"
              error={errors.password?.message}
              {...register("password")}
            />
            <button
              type="button"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2.5 top-[29px] inline-flex h-7 w-7 items-center justify-center rounded text-text-muted hover:text-text"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          <Button type="submit" loading={isSubmitting} className="w-full">
            Sign in
          </Button>
        </form>

        {showGoogle && (
          <>
            <div className="my-5 flex items-center gap-3 text-xs text-text-muted">
              <div className="h-px flex-1 bg-border" />
              <span>or</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <GoogleSignInButton
              portal={portal}
              mode="signin"
              onSuccess={(u) => {
                setUser(u);
                redirectAfterLogin(u);
              }}
              onError={(msg) => setFormError(msg)}
            />
          </>
        )}

        {showSignupLink && (
          <p className="mt-6 text-center text-sm text-text-muted">
            New here?{" "}
            <Link href="/signup" className="font-medium text-accent hover:underline">
              Create an account
            </Link>
          </p>
        )}
      </div>
    </AuthSplitShell>
  );
}

export function RoleLoginForm(props: {
  portal: UserRole;
  title: string;
  subtitle: string;
  badge?: string;
  showGoogle?: boolean;
  showSignupLink?: boolean;
}) {
  return (
    <Suspense fallback={<BrandLoader fullScreen label="Loading…" />}>
      <RoleLoginInner {...props} />
    </Suspense>
  );
}
