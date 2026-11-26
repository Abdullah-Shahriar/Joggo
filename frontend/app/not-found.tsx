"use client";

import Link from "next/link";

import { AppLayout } from "@/components/layout/AppLayout";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { useAuth } from "@/lib/auth";
import { getRoleHome } from "@/lib/constants";

function NotFoundBody({ href, label }: { href: string; label: string }) {
  return (
    <div className="mx-auto flex max-w-prose flex-col items-center justify-center px-4 py-24 text-center">
      <p className="text-5xl font-semibold tracking-tight text-text">404</p>
      <div className="mt-2 h-0.5 w-12 bg-accent" />
      <h1 className="mt-5 text-xl font-semibold text-text">This page doesn&apos;t exist</h1>
      <p className="mt-2 text-sm text-text-muted">
        The link may be broken or the page was moved.
      </p>
      <Link
        href={href}
        className="mt-6 inline-flex h-10 items-center justify-center rounded bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
      >
        {label}
      </Link>
    </div>
  );
}

export default function NotFoundPage() {
  const { user } = useAuth();

  if (user) {
    return (
      <AppLayout>
        <NotFoundBody href={getRoleHome(user.role)} label="Go to dashboard" />
      </AppLayout>
    );
  }

  return (
    <PublicLayout redirectIfAuthenticated={false}>
      <NotFoundBody href="/" label="Go to home" />
    </PublicLayout>
  );
}
