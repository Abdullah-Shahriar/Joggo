import type { Metadata } from "next";
import { AlertCircle, EyeOff, FileWarning, ShieldAlert, ShieldPlus } from "lucide-react";
import Link from "next/link";

import { PublicLayout } from "@/components/layout/PublicLayout";
import { TokenChip } from "@/components/ui/TokenChip";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `${APP_NAME} — Use AI on Patient Records Without Exposing Patients`,
  description:
    "Upload patient PDFs or photos, remove personal details with safe labels, run a second safety check, review side-by-side, and approve before generating clinical drafts.",
};

const PROBLEM_POINTS = [
  {
    icon: ShieldAlert,
    title: "Pasting patient files into AI risks privacy",
    detail:
      "Doctors want faster help with discharge summaries and notes, but regular AI tools are not safe for real patient names, phone numbers, or record IDs.",
  },
  {
    icon: AlertCircle,
    title: "Total AI bans leave staff overloaded",
    detail:
      "Blocking AI completely forces busy clinicians back into slow manual paperwork—or pushes people toward unsafe, unmonitored workarounds.",
  },
  {
    icon: EyeOff,
    title: "Basic black-bar hiding breaks the medical story",
    detail:
      "Simply erasing every name and date removes ages and visit timelines, leaving the AI unable to write an accurate clinical summary.",
  },
  {
    icon: FileWarning,
    title: "Private details hide outside the main paragraphs",
    detail:
      "Patient names and numbers often sit inside scanned headers, notes, form fields, photos, or file properties that quick manual checks miss.",
  },
];

const STEPS = [
  "Upload a patient PDF, image (PNG, JPG, SVG), or take a photo with your camera.",
  "Personal details like names, phone numbers, and dates are automatically replaced with safe labels.",
  "You review the cleaned page side-by-side with the original and approve it.",
  "The writing assistant prepares your clinical draft, and real details are restored only on your screen.",
];

const SAFETY_POINTS = [
  "Names, phone numbers and addresses are removed, double-checked, and approved by you before anything is sent to an AI service.",
  "Dates are turned into day counts (such as Day 0 and Day 3), and birthdates become age.",
  "Real details stay only in temporary private memory and clear automatically when you sign out.",
  "Every important action is recorded in a tamper-evident activity history (any change is detected).",
];

export default function LandingPage() {
  return (
    <PublicLayout>
      {/* Band 1: Hero (white) */}
      <section className="bg-bg py-12 sm:py-16 lg:py-24">
        <div className="mx-auto grid max-w-app items-center gap-10 px-4 sm:px-6 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-7">
            <span className="inline-flex items-center rounded-full border border-accent/25 bg-accent-tint px-3 py-1 text-xs font-semibold text-accent">
              Privacy-first AI for medical documents
            </span>
            <h1 className="mt-4 text-[30px] font-semibold leading-tight tracking-tight text-text sm:text-[40px] lg:text-[44px]">
              Use AI on patient records. Without exposing patients.
            </h1>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-text-muted sm:text-base">
              {APP_NAME} removes personal details, runs a second safety check, and waits for your
              approval before anything reaches an AI writing assistant, then puts the real details
              back only on your screen.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="/login"
                className="joggo-btn-primary-elevated inline-flex h-11 items-center justify-center rounded bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
              >
                Get started
              </Link>
              <a
                href="#the-problem"
                className="joggo-btn-elevated inline-flex h-11 items-center justify-center rounded border border-border bg-bg px-5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                Why {APP_NAME}?
              </a>
              <a
                href="#how-it-works"
                className="joggo-btn-elevated inline-flex h-11 items-center justify-center rounded border border-border bg-bg px-5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                How it works
              </a>
            </div>
          </div>

          {/* Flat overlapping clinical chart cards */}
          <div className="mx-auto w-full max-w-[420px] lg:col-span-5 lg:max-w-none" aria-hidden="true">
            <div className="w-full">
              {/* Back card: Original admission form */}
              <div className="joggo-surface-sep w-[84%] rounded-[8px] border border-border bg-bg px-4 pb-8 pt-3.5 sm:w-[82%]">
                <div className="joggo-divider-sep flex items-center justify-between gap-2 pb-2">
                  <span className="text-[13px] font-medium text-text">Admission form</span>
                  <span className="font-mono text-[11px] font-medium tracking-wide text-text-muted">
                    WARD 4
                  </span>
                </div>
                <dl className="mt-2.5 space-y-1.5 text-[13px] leading-snug">
                  <div className="flex items-baseline gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">Name</dt>
                    <dd className="text-text">Rahim Uddin</dd>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">DOB</dt>
                    <dd className="text-text">03.05.1968</dd>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">MRN</dt>
                    <dd className="text-text">HN-55821</dd>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">Dx</dt>
                    <dd className="text-text">Pneumonia</dd>
                  </div>
                </dl>
              </div>

              {/* Front card: De-identified record sent to AI */}
              <div className="joggo-surface-sep relative z-10 -mt-5 ml-auto w-[84%] rounded-[8px] border border-accent bg-bg px-4 py-3.5 sm:w-[82%]">
                <div className="flex items-center justify-between gap-2 border-b border-accent pb-2 shadow-[0_1px_0_rgba(15,118,110,0.16)]">
                  <span className="text-[13px] font-medium text-text">Sent to AI</span>
                  <span className="font-mono text-[11px] font-medium tracking-wide text-accent">
                    CLEAN
                  </span>
                </div>
                <dl className="mt-2.5 space-y-1.5 text-[13px] leading-snug">
                  <div className="flex items-center gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">Name</dt>
                    <dd>
                      <TokenChip>[PATIENT_A]</TokenChip>
                    </dd>
                  </div>
                  <div className="flex items-center gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">DOB</dt>
                    <dd>
                      <TokenChip>Age 58</TokenChip>
                    </dd>
                  </div>
                  <div className="flex items-center gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">MRN</dt>
                    <dd>
                      <TokenChip>[MRN_1]</TokenChip>
                    </dd>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <dt className="w-10 shrink-0 text-text-muted">Dx</dt>
                    <dd className="text-text">Pneumonia</dd>
                  </div>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Band 2: Highlighted Problem Statement (bg-subtle) */}
      <section id="the-problem" className="border-y border-border bg-bg-subtle py-14 shadow-[inset_0_1px_0_rgba(17,24,39,0.03),0_1px_0_rgba(17,24,39,0.04)] sm:py-16">
        <div className="mx-auto max-w-app px-4 sm:px-6">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-accent">
              The problem {APP_NAME} solves
            </p>
            <h2 className="mt-2 text-2xl font-semibold leading-snug text-text sm:text-[28px]">
              Clinicians need AI help with paperwork—but patient records can&apos;t safely be shared
              with outside AI tools.
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-text-muted">
              Every day, doctors spend hours writing discharge summaries, case notes, and care plans.
              Using standard AI tools risks leaking private patient details, while avoiding AI keeps
              paperwork slow and exhausting.
            </p>
          </div>

          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {PROBLEM_POINTS.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.title}
                  className="rounded-lg border border-border bg-bg p-5 shadow-[0_1px_4px_rgba(17,24,39,0.05)]"
                >
                  <div className="flex items-start gap-3.5">
                    <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-danger-tint text-danger">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="text-base font-semibold text-text">{item.title}</h3>
                      <p className="mt-1.5 text-[15px] leading-relaxed text-text-muted">
                        {item.detail}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Band 3: How it works (white) */}
      <section id="how-it-works" className="bg-bg py-14 sm:py-16">
        <div className="mx-auto max-w-prose px-4 sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-accent">
            How {APP_NAME} solves it
          </p>
          <h2 className="mt-1.5 text-2xl font-semibold text-text">How it works</h2>
          <ol className="mt-6 space-y-4">
            {STEPS.map((step, idx) => (
              <li key={step} className="flex items-start gap-4 text-[15px] leading-relaxed text-text">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent-tint text-xs font-semibold text-accent">
                  {idx + 1}
                </span>
                <span className="pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Band 4: Why it is safe (bg-subtle) */}
      <section className="border-y border-border bg-bg-subtle py-14 shadow-[inset_0_1px_0_rgba(17,24,39,0.03),0_1px_0_rgba(17,24,39,0.04)] sm:py-16">
        <div className="mx-auto max-w-prose px-4 sm:px-6">
          <h2 className="flex items-center gap-2 text-2xl font-semibold text-text">
            <ShieldPlus className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
            <span>Why it is safe</span>
          </h2>
          <ul className="mt-6 space-y-3 text-[15px] leading-relaxed text-text">
            {SAFETY_POINTS.map((point) => (
              <li key={point} className="flex items-start gap-3">
                <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Band 5: Final CTA (white) */}
      <section className="bg-bg py-14 sm:py-16">
        <div className="mx-auto max-w-prose px-4 text-center sm:px-6">
          <h2 className="text-xl font-semibold text-text">Try it with sample records</h2>
          <p className="mt-2 text-[15px] text-text-muted">
            Sign in with a demo account or create one to try the full privacy-safe drafting flow.
          </p>
          <div className="mt-6">
            <Link
              href="/login"
              className="joggo-btn-primary-elevated inline-flex h-11 items-center justify-center rounded bg-accent px-6 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Get started
            </Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
