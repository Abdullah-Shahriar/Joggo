"use client";

import React from "react";
import Link from "next/link";
import { NotepadTextDashed } from "lucide-react";

import { cn } from "@/lib/utils";

export interface FooterLink {
  label: string;
  href: string;
}

export interface SocialLink {
  icon: React.ReactNode;
  href: string;
  label: string;
}

export interface FooterProps {
  brandName?: string;
  brandHref?: string;
  brandDescription?: string;
  contactEmail?: string;
  socialLinks?: SocialLink[];
  navLinks?: FooterLink[];
  creatorName?: string;
  creatorUrl?: string;
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
  socialLinks = [],
  navLinks = [],
  creatorName,
  creatorUrl,
  rightNotice,
  brandIcon,
  brandIconContainerClassName,
  className,
}: FooterProps) => {
  const currentYear = Math.max(2026, new Date().getFullYear());

  return (
    <section className={cn("relative w-full mt-0 overflow-x-clip overflow-y-hidden", className)}>
      <footer className="border-t border-border bg-background mt-12 sm:mt-16 relative">
        <div className="max-w-7xl flex flex-col justify-between mx-auto min-h-[28rem] sm:min-h-[33rem] md:min-h-[38rem] relative px-4 pt-10 pb-8 sm:px-6">
          <div className="flex flex-col mb-16 sm:mb-20 md:mb-0 w-full">
            <div className="w-full flex flex-col items-center">
              <div className="space-y-2 flex flex-col items-center flex-1">
                <Link
                  href={brandHref}
                  aria-label={`${brandName} home`}
                  className="flex items-center gap-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <span className="text-foreground text-3xl font-bold hover:text-accent transition-colors">
                    {brandName}
                  </span>
                </Link>
                <p className="text-muted-foreground font-semibold text-center w-full max-w-sm px-2 sm:px-0">
                  {brandDescription}
                </p>
                {contactEmail && (
                  <a
                    href={`mailto:${contactEmail}`}
                    className="text-sm font-medium text-accent hover:underline break-all"
                  >
                    {contactEmail}
                  </a>
                )}
              </div>

              {socialLinks.length > 0 && (
                <div className="flex mb-8 mt-3 gap-4">
                  {socialLinks.map((link, index) => (
                    <Link
                      key={index}
                      href={link.href}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <div className="w-6 h-6 hover:scale-110 duration-300">
                        {link.icon}
                      </div>
                      <span className="sr-only">{link.label}</span>
                    </Link>
                  ))}
                </div>
              )}

              {navLinks.length > 0 && (
                <nav
                  aria-label="Footer navigation"
                  className={cn(
                    "flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm font-medium text-muted-foreground max-w-full px-2 sm:px-4",
                    socialLinks.length === 0 && "mt-5"
                  )}
                >
                  {navLinks.map((link, index) => (
                    <Link
                      key={index}
                      className="hover:text-foreground duration-300 hover:font-semibold"
                      href={link.href}
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              )}
            </div>
          </div>

          <div className="mt-24 sm:mt-24 md:mt-24 flex flex-col gap-2 md:gap-1 items-center justify-center md:flex-row md:items-center md:justify-between px-2 sm:px-4 md:px-0 relative z-20">
            <p
              suppressHydrationWarning
              className="text-sm sm:text-base text-muted-foreground text-center md:text-left"
            >
              © {currentYear} {brandName}. All rights reserved.
            </p>
            {creatorName && creatorUrl ? (
              <nav className="flex gap-4">
                <Link
                  href={creatorUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm sm:text-base text-muted-foreground hover:text-foreground transition-colors duration-300 hover:font-medium"
                >
                  Crafted by {creatorName}
                </Link>
              </nav>
            ) : rightNotice ? (
              <p className="text-xs sm:text-sm text-muted-foreground text-center md:text-right">
                {rightNotice}
              </p>
            ) : null}
          </div>
        </div>

        {/* Large background watermark text */}
        <div
          aria-hidden="true"
          className="bg-gradient-to-b from-foreground/20 via-foreground/10 to-transparent bg-clip-text text-transparent leading-none absolute left-1/2 -translate-x-1/2 bottom-44 sm:bottom-40 md:bottom-32 font-extrabold tracking-tighter pointer-events-none select-none text-center px-4 whitespace-nowrap"
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
          className="absolute hover:border-accent transition-colors duration-400 drop-shadow-[0_0px_20px_rgba(15,118,110,0.22)] bottom-28 sm:bottom-24 md:bottom-20 backdrop-blur-sm rounded-3xl bg-background/80 left-1/2 border-2 border-border flex items-center justify-center p-2.5 sm:p-3 -translate-x-1/2 z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <div
            className={cn(
              "w-12 sm:w-16 md:w-24 h-12 sm:h-16 md:h-24 rounded-2xl flex items-center justify-center shadow-lg",
              brandIconContainerClassName ||
                "bg-gradient-to-br from-foreground to-foreground/80"
            )}
          >
            {brandIcon || (
              <NotepadTextDashed className="w-8 sm:w-10 md:w-14 h-8 sm:h-10 md:h-14 text-background drop-shadow-lg" />
            )}
          </div>
        </Link>

        {/* Bottom horizontal hairline */}
        <div
          aria-hidden="true"
          className="absolute bottom-32 sm:bottom-34 backdrop-blur-sm h-1 bg-gradient-to-r from-transparent via-border to-transparent w-full left-1/2 -translate-x-1/2"
        />

        {/* Bottom soft fade shadow */}
        <div
          aria-hidden="true"
          className="bg-gradient-to-t from-background via-background/80 blur-[1em] to-background/40 absolute bottom-28 w-full h-24 pointer-events-none"
        />
      </footer>
    </section>
  );
};
