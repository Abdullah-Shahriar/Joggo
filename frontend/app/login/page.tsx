"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/FormFields";
import { Logo } from "@/components/ui/Logo";
import { ApiError, apiRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getRoleHome } from "@/lib/constants";
import type { AuthSessionResponse, AuthUser } from "@/lib/types";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

function LoginContent() {
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
      const nextParam = searchParams.get("next");
      if (nextParam && nextParam.startsWith("/") && !nextParam.startsWith("//")) {
        router.replace(nextParam);
        return;
      }
      router.replace(getRoleHome(loggedInUser.role));
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
        body: values,
        silentErrorToast: true,
      });
      setUser(data.user);
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
    <div className="min-h-screen bg-bg px-4 py-6">
      <div className="mx-auto max-w-app">
        <Link
          href="/"
          className="inline-flex h-10 items-center gap-2 rounded px-3 text-sm font-medium text-text hover:bg-bg-subtle"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to home</span>
        </Link>
      </div>

      <main className="mx-auto mt-10 w-full max-w-[400px]">
        <div className="mb-6 flex justify-center">
          <Logo />
        </div>

        <div className="rounded border border-border bg-bg p-6">
          <h1 className="text-xl font-semibold text-text">Sign in</h1>

          {formError && (
            <div role="alert" className="mt-4 rounded bg-danger-tint px-3 py-2.5 text-xs text-danger">
              {formError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4" noValidate>
            <Input
              id="login-email"
              label="Email"
              type="email"
              autoComplete="email"
              error={errors.email?.message}
              {...register("email")}
            />

            <div className="relative">
              <Input
                id="login-password"
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

          <div className="my-5 flex items-center gap-3 text-xs text-text-muted">
            <div className="h-px flex-1 bg-border" />
            <span>or</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <GoogleSignInButton
            onSuccess={(u) => {
              setUser(u);
              redirectAfterLogin(u);
            }}
            onError={(msg) => setFormError(msg)}
          />

          <p className="mt-5 text-center text-xs text-text-muted">
            New here?{" "}
            <Link href="/signup" className="font-medium text-accent hover:underline">
              Create an account
            </Link>
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-text-muted">
          Demo environment — use synthetic data only
        </p>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<BrandLoader fullScreen label="Loading…" />}>
      <LoginContent />
    </Suspense>
  );
}
