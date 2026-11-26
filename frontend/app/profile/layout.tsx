import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Profile & Sessions",
  description: "Update your clinician profile, change your password, and manage active sign-in sessions in JOGGO.",
};

export default function ProfileLayout({ children }: { children: ReactNode }) {
  return children;
}
