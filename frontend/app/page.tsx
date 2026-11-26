import type { Metadata } from "next";
import { AlertCircle, EyeOff, FileWarning, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { PublicLayout } from "@/components/layout/PublicLayout";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `${APP_NAME} — Use AI on Patient Records Without Exposing Patients`,
  description:
    "Upload patient PDFs or photos, hide personal details automatically with safe labels, review side-by-side, and generate clinical drafts without leaking PHI.",
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
  "Patient names, phone numbers, and addresses are never sent to outside AI services.",
  "Dates are turned into day counts (such as Day 0 and Day 3), and birthdates become age.",
  "Real details stay only in temporary private memory and clear automatically when you sign out.",
  "Every important action is recorded in a permanent activity history that cannot be altered.",
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
              {APP_NAME} hides personal details before anything reaches an AI writing assistant,
              then puts the real details back only on your screen.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="/login"
                className="inline-flex h-11 items-center justify-center rounded bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
              >
                Get started
              </Link>
              <a
                href="#the-problem"
                className="inline-flex h-11 items-center justify-center rounded border border-border bg-bg px-5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                Why {APP_NAME}?
              </a>
              <a
                href="#how-it-works"
                className="inline-flex h-11 items-center justify-center rounded border border-border bg-bg px-5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                How it works
              </a>
            </div>
          </div>

          {/* Subtle flat illustration */}
          <div className="mx-auto w-full max-w-[420px] lg:col-span-5 lg:max-w-none" aria-hidden="true">
            <svg viewBox="0 0 380 260" className="w-full" fill="none">
              <rect x="20" y="20" width="140" height="190" rx="6" fill="#FFFFFF" stroke="#E5E7EB" strokeWidth="1.5" />
              <rect x="36" y="42" width="68" height="8" rx="3" fill="#111827" />
              <rect x="36" y="62" width="96" height="8" rx="3" fill="#E6F4F1" />
              <rect x="36" y="80" width="84" height="6" rx="3" fill="#E5E7EB" />
              <rect x="36" y="96" width="104" height="6" rx="3" fill="#E5E7EB" />
              <rect x="36" y="114" width="76" height="8" rx="3" fill="#E6F4F1" />
              <rect x="36" y="134" width="96" height="6" rx="3" fill="#E5E7EB" />
              <rect x="36" y="150" width="88" height="6" rx="3" fill="#E5E7EB" />

              <path d="M170 115h40" stroke="#0F766E" strokeWidth="2" strokeLinecap="round" />
              <path d="M202 109l8 6-8 6" stroke="#0F766E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

              <rect x="220" y="34" width="140" height="190" rx="6" fill="#F7F8F9" stroke="#E5E7EB" strokeWidth="1.5" />
              <rect x="236" y="56" width="88" height="14" rx="4" fill="#E6F4F1" />
              <text x="243" y="66" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                [PATIENT_A]
              </text>
              <rect x="236" y="82" width="54" height="14" rx="4" fill="#E6F4F1" />
              <text x="243" y="92" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                Age 58
              </text>
              <rect x="296" y="82" width="50" height="14" rx="4" fill="#E6F4F1" />
              <text x="302" y="92" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                [DAY_0]
              </text>
              <rect x="236" y="112" width="104" height="6" rx="3" fill="#E5E7EB" />
              <rect x="236" y="128" width="92" height="6" rx="3" fill="#E5E7EB" />
              <rect x="236" y="144" width="98" height="6" rx="3" fill="#E5E7EB" />
              <rect x="236" y="160" width="76" height="6" rx="3" fill="#E5E7EB" />
            </svg>
          </div>
        </div>
      </section>

      {/* Band 2: Highlighted Problem Statement (bg-subtle) */}
      <section id="the-problem" className="border-y border-border bg-bg-subtle py-14 sm:py-16">
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
      <section className="border-y border-border bg-bg-subtle py-14 sm:py-16">
        <div className="mx-auto max-w-prose px-4 sm:px-6">
          <h2 className="text-2xl font-semibold text-text">Why it is safe</h2>
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
              className="inline-flex h-11 items-center justify-center rounded bg-accent px-6 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Get started
            </Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
