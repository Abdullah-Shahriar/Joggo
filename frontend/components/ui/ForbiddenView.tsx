"use client";

import { useRouter } from "next/navigation";

import { Button } from "./Button";

export function ForbiddenView() {
  const router = useRouter();
  return (
    <div className="mx-auto flex max-w-prose flex-col items-center justify-center py-20 text-center">
      <p className="text-4xl font-semibold text-text">403</p>
      <div className="mt-2 h-0.5 w-10 bg-accent" />
      <h1 className="mt-4 text-xl font-semibold text-text">You don&apos;t have access to this page.</h1>
      <div className="mt-6">
        <Button variant="secondary" onClick={() => router.back()}>
          Go back
        </Button>
      </div>
    </div>
  );
}
