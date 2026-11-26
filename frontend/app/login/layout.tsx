import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Sign In",
  description: "Sign in to your JOGGO clinician workspace to upload, review, and draft privacy-safe clinical documents.",
};

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children;
}
