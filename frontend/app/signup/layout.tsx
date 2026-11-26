import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Create Account",
  description: "Create a JOGGO account with email or Google to test privacy-first clinical document de-identification and AI drafting.",
};

export default function SignupLayout({ children }: { children: ReactNode }) {
  return children;
}
