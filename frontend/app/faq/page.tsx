"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { PublicLayout } from "@/components/layout/PublicLayout";

const FAQ_ITEMS = [
  {
    q: "Does patient data reach the AI?",
    a: "No. Only placeholder text such as [PATIENT_A], \"Age 58\" and [DAY_0].",
  },
  {
    q: "What if something is missed?",
    a: "A second scan blocks sending if it finds leftovers, and you can highlight any text to replace it.",
  },
  {
    q: "Where are real names stored?",
    a: "Only in temporary encrypted memory during your session. They are wiped on sign out or after 30 minutes idle.",
  },
  {
    q: "Can administrators read my documents?",
    a: "No. Admins can manage accounts and see activity logs, never document content.",
  },
  {
    q: "Which AI providers are used?",
    a: "Gemini and Groq. If one fails, the other is used automatically.",
  },
  {
    q: "Is this ready for real patients?",
    a: "This is a demo. Use synthetic data only.",
  },
];

export default function FaqPage() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  return (
    <PublicLayout>
      <div className="mx-auto max-w-prose px-4 py-16 sm:px-6">
        <h1 className="text-[28px] font-semibold text-text">Frequently asked questions</h1>
        <p className="mt-2 text-sm text-text-muted">
          Key details on privacy, temporary memory, and AI safety.
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
                    <p className="pb-4 text-sm text-text-muted">{item.a}</p>
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
