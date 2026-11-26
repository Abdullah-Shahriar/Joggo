"use client";

import { ArrowLeft, FileCheck2, Lock, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";

const TRUST_SIGNALS = [
  {
    icon: ShieldCheck,
    title: "Local HIPAA-18 scrubbing",
    detail: "Names, dates, phone numbers, MRNs, and metadata are tokenized before any AI request.",
  },
  {
    icon: Lock,
    title: "Temporary encrypted memory",
    detail: "Real patient details remain in an AES-256-GCM session vault and wipe on sign out.",
  },
  {
    icon: FileCheck2,
    title: "Clinician approval & audit trail",
    detail: "Nothing sends automatically. Every action is logged in a hash-chained audit record.",
  },
];

export function AuthSplitShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 bg-bg lg:grid-cols-2">
      {/* Left 50% pane: Trust visual & clinical confidentiality messaging */}
      <aside
        aria-label="Security and privacy overview"
        className="flex flex-col justify-between border-b border-border bg-bg-subtle px-6 py-8 sm:px-10 lg:border-b-0 lg:border-r lg:px-14 lg:py-12"
      >
        <div>
          <Link href="/" className="inline-flex items-center">
            <Logo />
          </Link>

          <div className="mt-10 max-w-md lg:mt-16">
            {/* Flat clinical privacy illustration */}
            <svg
              aria-hidden="true"
              viewBox="0 0 360 170"
              className="w-full max-w-[340px]"
              fill="none"
            >
              <rect
                x="4"
                y="12"
                width="148"
                height="146"
                rx="8"
                fill="#FFFFFF"
                stroke="#D1D5DB"
                strokeWidth="1.5"
              />
              <rect x="20" y="30" width="76" height="8" rx="3" fill="#111827" />
              <rect x="20" y="48" width="110" height="10" rx="3" fill="#FEF2F2" stroke="#B91C1C" strokeOpacity="0.35" />
              <rect x="20" y="68" width="94" height="7" rx="3" fill="#E5E7EB" />
              <rect x="20" y="84" width="108" height="7" rx="3" fill="#E5E7EB" />
              <rect x="20" y="102" width="84" height="10" rx="3" fill="#FEF2F2" stroke="#B91C1C" strokeOpacity="0.35" />
              <rect x="20" y="122" width="98" height="7" rx="3" fill="#E5E7EB" />

              <circle cx="180" cy="85" r="18" fill="#E6F4F1" stroke="#0F766E" strokeWidth="1.5" />
              <path
                d="M180 75l-7 3v5c0 4.2 3 7.2 7 8.2 4-1 7-4 7-8.2v-5l-7-3z"
                stroke="#0F766E"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              <path d="M180 80v6M177 83h6" stroke="#0F766E" strokeWidth="1.5" strokeLinecap="round" />

              <rect
                x="208"
                y="12"
                width="148"
                height="146"
                rx="8"
                fill="#FFFFFF"
                stroke="#0F766E"
                strokeWidth="1.5"
              />
              <rect x="224" y="30" width="86" height="14" rx="4" fill="#E6F4F1" />
              <text x="231" y="40" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                [PATIENT_A]
              </text>
              <rect x="224" y="52" width="52" height="14" rx="4" fill="#E6F4F1" />
              <text x="231" y="62" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                Age 58
              </text>
              <rect x="282" y="52" width="52" height="14" rx="4" fill="#E6F4F1" />
              <text x="289" y="62" fill="#0F766E" fontSize="9" fontFamily="sans-serif" fontWeight="600">
                [DAY_0]
              </text>
              <rect x="224" y="78" width="110" height="7" rx="3" fill="#E5E7EB" />
              <rect x="224" y="94" width="96" height="7" rx="3" fill="#E5E7EB" />
              <rect x="224" y="110" width="104" height="7" rx="3" fill="#E5E7EB" />
              <rect x="224" y="126" width="82" height="7" rx="3" fill="#E5E7EB" />
            </svg>

            <h2 className="mt-8 text-2xl font-semibold leading-snug text-text">
              Built for clinical confidentiality.
            </h2>
            <p className="mt-2.5 text-[15px] leading-relaxed text-text-muted">
              De-identify patient PDFs locally, verify every placeholder, and restore real details
              only on your screen.
            </p>

            <ul className="mt-8 space-y-4">
              {TRUST_SIGNALS.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.title} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded bg-accent-tint text-accent">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-text">{item.title}</p>
                      <p className="mt-0.5 text-sm text-text-muted">{item.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <p className="mt-10 text-xs text-text-muted">
          Demo environment — use synthetic data only
        </p>
      </aside>

      {/* Right 50% pane: Back button + Auth form */}
      <div className="flex flex-col px-6 py-6 sm:px-10 lg:px-14">
        <div>
          <Link
            href="/"
            className="inline-flex h-10 items-center gap-2 rounded px-3 text-sm font-medium text-text hover:bg-bg-subtle"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to home</span>
          </Link>
        </div>

        <main className="mx-auto my-auto w-full max-w-[420px] py-8">{children}</main>
      </div>
    </div>
  );
}
