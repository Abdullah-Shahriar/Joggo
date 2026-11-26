"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthSplitShell } from "@/components/auth/AuthSplitShell";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { BrandLoader } from "@/components/ui/BrandLoader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/FormFields";
import { ApiError, apiRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getRoleHome } from "@/lib/constants";
import type { AuthSessionResponse } from "@/lib/types";

const signupSchema = z.object({
  full_name: z.string().trim().min(2, "Enter your full name (2–80 characters).").max(80),
  email: z.string().email("Enter a valid email address."),
  password: z
    .string()
    .min(10, "Password must be at least 10 characters.")
    .refine((v) => /[A-Za-z]/.test(v), "Include at least one letter.")
    .refine((v) => /\d/.test(v), "Include at least one digit."),
});

type SignupFormValues = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const router = useRouter();
  const { user, isLoading, setUser } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    watch,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
  });

  const passwordVal = watch("password") || "";
  const hasLen = passwordVal.length >= 10;
  const hasLetter = /[A-Za-z]/.test(passwordVal);
  const hasDigit = /\d/.test(passwordVal);

  useEffect(() => {
    if (!isLoading && user) {
      router.replace(getRoleHome(user.role));
    }
  }, [isLoading, user, router]);

  const onSubmit = async (values: SignupFormValues) => {
    setFormError(null);
    try {
      const data = await apiRequest<AuthSessionResponse>("/auth/signup", {
        method: "POST",
        body: values,
        silentErrorToast: true,
      });
      setUser(data.user);
      router.replace(getRoleHome(data.user.role));
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Unable to create account. Please try again.");
      }
    }
  };

  if (user) {
    return <BrandLoader fullScreen label="Redirecting…" />;
  }

  return (
    <AuthSplitShell>
      <div className="rounded border border-border bg-bg p-6 sm:p-8">
        <h1 className="text-2xl font-semibold text-text">Create an account</h1>
        <p className="mt-1.5 text-[15px] text-text-muted">
          Set up your account to start testing with sample patient documents and photos.
        </p>

        {formError && (
          <div role="alert" className="mt-4 rounded bg-danger-tint px-3.5 py-2.5 text-sm text-danger">
            {formError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <Input
            id="signup-name"
            label="Full name"
            type="text"
            autoComplete="name"
            error={errors.full_name?.message}
            {...register("full_name")}
          />

          <Input
            id="signup-email"
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />

          <div className="relative">
            <Input
              id="signup-password"
              label="Password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
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
            <ul className="mt-2 space-y-1 text-xs">
              {[
                { ok: hasLen, label: "At least 10 characters" },
                { ok: hasLetter, label: "At least one letter" },
                { ok: hasDigit, label: "At least one digit" },
              ].map((rule) => (
                <li
                  key={rule.label}
                  className={`flex items-center gap-1.5 ${
                    rule.ok ? "text-accent" : "text-text-muted"
                  }`}
                >
                  <Check className={`h-3.5 w-3.5 ${rule.ok ? "opacity-100" : "opacity-30"}`} />
                  <span>{rule.label}</span>
                </li>
              ))}
            </ul>
          </div>

          <Button type="submit" loading={isSubmitting} className="w-full">
            Create account
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
            router.replace(getRoleHome(u.role));
          }}
          onError={(msg) => setFormError(msg)}
        />

        <p className="mt-6 text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </AuthSplitShell>
  );
}
