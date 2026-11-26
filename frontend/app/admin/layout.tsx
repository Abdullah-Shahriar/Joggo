import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Administration",
  description: "Review aggregate usage analytics, user accounts, support tickets, and tamper-evident audit logs in JOGGO.",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  return children;
}
