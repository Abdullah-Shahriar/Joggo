import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "New Document",
  description: "Upload a patient PDF or photo or capture a page with your camera for automatic privacy de-identification.",
};

export default function NewDocumentLayout({ children }: { children: ReactNode }) {
  return children;
}
