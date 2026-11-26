import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "View your recent clinical documents, weekly completion stats, and activity overview in JOGGO.",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return children;
}
