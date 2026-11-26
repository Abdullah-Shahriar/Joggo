import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Administrator Portal",
  description: "Restricted administrator sign-in portal for JOGGO.",
  robots: { index: false, follow: false },
};

export default function AdminPortalLayout({ children }: { children: ReactNode }) {
  return children;
}
