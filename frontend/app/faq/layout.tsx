import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Plain-language answers about how JOGGO hides patient details, supported file formats, temporary private memory, and backup AI services.",
};

export default function FaqLayout({ children }: { children: ReactNode }) {
  return children;
}
