import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Help & Support",
  description: "Submit a support ticket, report a privacy concern, or track replies from the JOGGO administration team.",
};

export default function HelpLayout({ children }: { children: ReactNode }) {
  return children;
}
