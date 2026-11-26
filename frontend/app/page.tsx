import Link from "next/link";

import { PublicLayout } from "@/components/layout/PublicLayout";
import { APP_NAME } from "@/lib/constants";

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
      <section className="bg-bg py-16 sm:py-24">
        <div className="mx-auto grid max-w-app items-center gap-12 px-4 sm:px-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <h1 className="text-[34px] font-semibold leading-tight tracking-tight text-text sm:text-[44px]">
              Use AI on patient records. Without exposing patients.
            </h1>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-text-muted">
              {APP_NAME} hides personal details before anything reaches an AI writing assistant,
              then puts the real details back only on your screen.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/login"
                className="inline-flex h-10 items-center justify-center rounded bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
              >
                Get started
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex h-10 items-center justify-center rounded border border-border bg-bg px-5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                How it works
              </a>
            </div>
          </div>

          {/* Subtle flat illustration */}
          <div className="hidden lg:col-span-5 lg:block" aria-hidden="true">
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

      {/* Band 2: How it works (bg-subtle) */}
      <section id="how-it-works" className="border-y border-border bg-bg-subtle py-16">
        <div className="mx-auto max-w-prose px-4 sm:px-6">
          <h2 className="text-xl font-semibold text-text">How it works</h2>
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

      {/* Band 3: Why it is safe (white) */}
      <section className="bg-bg py-16">
        <div className="mx-auto max-w-prose px-4 sm:px-6">
          <h2 className="text-xl font-semibold text-text">Why it is safe</h2>
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

      {/* Band 4: Final CTA (bg-subtle) */}
      <section className="border-t border-border bg-bg-subtle py-16">
        <div className="mx-auto max-w-prose px-4 text-center sm:px-6">
          <h2 className="text-xl font-semibold text-text">Try it with sample records</h2>
          <p className="mt-2 text-[15px] text-text-muted">
            Sign in with a demo account or create one to try the full privacy-safe drafting flow.
          </p>
          <div className="mt-6">
            <Link
              href="/login"
              className="inline-flex h-10 items-center justify-center rounded bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Get started
            </Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
