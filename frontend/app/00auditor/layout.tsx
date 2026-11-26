import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Auditor Portal",
  description: "Restricted compliance auditor sign-in portal for JOGGO.",
  robots: { index: false, follow: false },
};

export default function AuditorPortalLayout({ children }: { children: ReactNode }) {
  return children;
}
