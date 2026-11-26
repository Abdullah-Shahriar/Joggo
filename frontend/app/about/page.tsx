import type { Metadata } from "next";
import { ShieldPlus } from "lucide-react";

import { PublicLayout } from "@/components/layout/PublicLayout";
import { TokenChip } from "@/components/ui/TokenChip";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: "About",
  description:
    "Learn how JOGGO protects patient privacy using local OCR, HIPAA-18 identifier detection, an encrypted in-memory vault, and tamper-evident audit logs.",
};

export default function AboutPage() {
  return (
    <PublicLayout>
      <article className="mx-auto max-w-prose px-4 py-16 sm:px-6">
        <h1 className="text-[28px] font-semibold text-text">About {APP_NAME}</h1>

        <section className="mt-8 space-y-3">
          <h2 className="text-xl font-semibold text-text">What {APP_NAME} does</h2>
          <p className="text-[15px] leading-relaxed text-text">
            {APP_NAME} helps doctors and care teams write discharge summaries, case summaries, and
            treatment plans faster with AI. Names, phone numbers and addresses are removed,
            double-checked, and approved by you before anything is sent to an AI service.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            You can upload a PDF, an image (PNG, JPG, or SVG), or snap a photo with your camera.{" "}
            {APP_NAME} reads the page privately, swaps personal details for clear labels like{" "}
            <TokenChip>[PATIENT_A]</TokenChip> and <TokenChip>Age 58</TokenChip>, and lets you
            review every change before anything is sent. When the draft is ready, the real details
            are restored only on your screen.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="text-xl font-semibold text-text">Why we built it</h2>
          <p className="text-[15px] leading-relaxed text-text">
            Many clinics ban AI tools out of concern for patient privacy, yet busy staff still need
            help with paperwork. Simple black-bar hiding removes ages and visit timelines, which
            makes medical summaries hard to write accurately.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            Patient documents can also hide names outside the main text—such as inside scanned
            headers, notes, form fields, or file properties. {APP_NAME} checks all of those places
            automatically.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-text">
            <ShieldPlus className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
            <span>How your privacy is protected</span>
          </h2>
          <p className="text-[15px] leading-relaxed text-text">
            {APP_NAME} reads typed and photographed pages directly on its own private server, finds
            personal details (names, phone numbers, addresses, medical record numbers, and exact
            dates), and runs a second safety check before you review the document. Real patient
            details stay only in locked temporary memory during your visit and are never saved to
            the permanent database or server logs.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            Every sign-in, document action, and account change is written to a tamper-evident
            activity history (any change is detected), so compliance reviewers can always verify how
            the system was used.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="text-xl font-semibold text-text">Important note</h2>
          <p className="text-[15px] leading-relaxed text-text">
            Automatic privacy checks are helpful, but no automated check is 100% perfect. That is
            why a doctor always reviews the cleaned document first and can highlight any remaining
            word to hide it everywhere before approving draft generation.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            This is a demonstration environment. Please use sample (synthetic) patient records only.
          </p>
        </section>
      </article>
    </PublicLayout>
  );
}
