"use client";

import React from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

interface FooterLink {
  label: string;
  href: string;
}

interface FooterProps {
  brandName?: string;
  brandHref?: string;
  brandDescription?: string;
  contactEmail?: string;
  navLinks?: FooterLink[];
  rightNotice?: string;
  brandIcon?: React.ReactNode;
  brandIconContainerClassName?: string;
  className?: string;
}

export const Footer = ({
  brandName = "JOGGO",
  brandHref = "/",
  brandDescription = "Privacy-first AI for medical documents.",
  contactEmail,
  navLinks = [],
  rightNotice,
  brandIcon,
  brandIconContainerClassName,
  className,
}: FooterProps) => {
  const currentYear = Math.max(2026, new Date().getFullYear());

  return (
    <section className={cn("relative mt-0 w-full overflow-x-clip overflow-y-hidden", className)}>
      <footer className="relative mt-12 border-t border-border bg-background sm:mt-16">
        <div className="relative mx-auto flex min-h-[28rem] max-w-7xl flex-col justify-between px-4 pb-8 pt-10 sm:min-h-[33rem] sm:px-6 md:min-h-[38rem]">
          <div className="mb-16 flex w-full flex-col sm:mb-20 md:mb-0">
            <div className="flex w-full flex-col items-center">
              <div className="flex flex-1 flex-col items-center space-y-2">
                <Link
                  href={brandHref}
                  aria-label={`${brandName} home`}
                  className="flex items-center gap-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <span className="text-3xl font-bold text-foreground transition-colors hover:text-accent">
                    {brandName}
                  </span>
                </Link>
                <p className="w-full max-w-sm px-2 text-center font-semibold text-muted-foreground sm:px-0">
                  {brandDescription}
                </p>
                {contactEmail && (
                  <a
                    href={`mailto:${contactEmail}`}
                    className="break-all text-sm font-medium text-accent hover:underline"
                  >
                    {contactEmail}
                  </a>
                )}
              </div>

              {navLinks.length > 0 && (
                <nav
                  aria-label="Footer navigation"
                  className="mt-5 flex max-w-full flex-wrap justify-center gap-x-5 gap-y-2 px-2 text-sm font-medium text-muted-foreground sm:px-4"
                >
                  {navLinks.map((link) => (
                    <Link
                      key={link.href}
                      className="duration-300 hover:font-semibold hover:text-foreground"
                      href={link.href}
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              )}
            </div>
          </div>

          <div className="relative z-20 mt-24 flex flex-col items-center justify-center gap-2 px-2 sm:px-4 md:flex-row md:items-center md:justify-between md:gap-1 md:px-0">
            <p
              suppressHydrationWarning
              className="text-center text-sm text-muted-foreground sm:text-base md:text-left"
            >
              © {currentYear} {brandName}. All rights reserved.
            </p>
            {rightNotice && (
              <p className="text-center text-xs text-muted-foreground sm:text-sm md:text-right">
                {rightNotice}
              </p>
            )}
          </div>
        </div>

        {/* Large background watermark text */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute bottom-44 left-1/2 -translate-x-1/2 select-none whitespace-nowrap bg-gradient-to-b from-foreground/20 via-foreground/10 to-transparent bg-clip-text px-4 text-center font-extrabold leading-none tracking-tighter text-transparent sm:bottom-40 md:bottom-32"
          style={{
            fontSize: "clamp(2.5rem, 11vw, 9.5rem)",
            maxWidth: "95vw",
          }}
        >
          {brandName.toUpperCase()}
        </div>

        {/* Bottom floating clickable logo badge */}
        <Link
          href={brandHref}
          aria-label={`Go to ${brandName} home`}
          className="duration-400 absolute bottom-28 left-1/2 z-10 flex -translate-x-1/2 items-center justify-center rounded-3xl border-2 border-border bg-background/80 p-2.5 drop-shadow-[0_0px_20px_rgba(15,118,110,0.22)] backdrop-blur-sm transition-colors hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:bottom-24 sm:p-3 md:bottom-20"
        >
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-2xl shadow-lg sm:h-16 sm:w-16 md:h-24 md:w-24",
              brandIconContainerClassName || "bg-gradient-to-br from-bg to-accent-tint",
            )}
          >
            {brandIcon}
          </div>
        </Link>

        {/* Bottom horizontal hairline */}
        <div
          aria-hidden="true"
          className="sm:bottom-34 absolute bottom-32 left-1/2 h-1 w-full -translate-x-1/2 bg-gradient-to-r from-transparent via-border to-transparent backdrop-blur-sm"
        />

        {/* Bottom soft fade shadow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute bottom-28 h-24 w-full bg-gradient-to-t from-background via-background/80 to-background/40 blur-[1em]"
        />
      </footer>
    </section>
  );
};
