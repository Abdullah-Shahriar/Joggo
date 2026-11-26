"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { PublicLayout } from "@/components/layout/PublicLayout";
import { APP_NAME } from "@/lib/constants";

const FAQ_ITEMS = [
  {
    q: "Does real patient information reach the AI?",
    a: "No. Detection is not perfect, so a second safety check and your review are required before sending. Only the cleaned version with safe labels—such as [PATIENT_A], Age 58, and [DAY_0]—is sent to the AI writing assistant.",
  },
  {
    q: "What file types can I upload?",
    a: "You can upload PDF, PNG, JPG, and SVG files, or use your device camera to take a photo of a printed page directly inside the app.",
  },
  {
    q: "What if a name or number is missed?",
    a: "A second safety check blocks sending if any personal detail is still visible. You can also highlight any word on the cleaned page to hide it everywhere in one click.",
  },
  {
    q: "Where are real names stored?",
    a: "Only in temporary private memory while you are signed in. They are wiped automatically when you sign out or after 30 minutes of inactivity.",
  },
  {
    q: "Can administrators read my documents?",
    a: "No. Administrators can manage accounts and review general activity counts, never the contents of any patient document.",
  },
  {
    q: "What happens if an AI service is busy or unavailable?",
    a: `${APP_NAME} automatically switches to a backup AI writing service so your draft can still be completed smoothly.`,
  },
  {
    q: "Is this demo ready for real patient records?",
    a: "This is a demonstration environment. Please use sample (synthetic) data only.",
  },
];

export default function FaqPage() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  return (
    <PublicLayout>
      <div className="mx-auto max-w-prose px-4 py-16 sm:px-6">
        <h1 className="text-[28px] font-semibold text-text">Frequently asked questions</h1>
        <p className="mt-2 text-[15px] text-text-muted">
          Plain-language answers about privacy, supported files, and how {APP_NAME} works.
        </p>

        <div className="mt-8 divide-y divide-border border-y border-border">
          {FAQ_ITEMS.map((item, idx) => {
            const isOpen = openIdx === idx;
            return (
              <div key={item.q}>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpenIdx(isOpen ? null : idx)}
                  className="flex w-full items-center justify-between gap-4 py-4 text-left text-base font-medium text-text hover:text-accent"
                >
                  <span>{item.q}</span>
                  <ChevronDown
                    aria-hidden="true"
                    className={`h-4 w-4 shrink-0 text-text-muted transition-transform duration-150 ${
                      isOpen ? "rotate-180 text-accent" : ""
                    }`}
                  />
                </button>
                <div
                  className={`grid transition-[grid-template-rows] duration-150 ease-out ${
                    isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="pb-4 text-[15px] leading-relaxed text-text-muted">{item.a}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </PublicLayout>
  );
}
