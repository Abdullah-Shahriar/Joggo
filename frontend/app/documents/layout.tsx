import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Documents",
  description: "Manage, review, resolve conflicts, and export your privacy-protected clinical documents in JOGGO.",
};

export default function DocumentsLayout({ children }: { children: ReactNode }) {
  return children;
}
