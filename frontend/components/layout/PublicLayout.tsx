"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BrandLoader } from "@/components/ui/BrandLoader";
import { Logo } from "@/components/ui/Logo";
import { Footer } from "@/components/ui/modem-animated-footer";
import { useAuth } from "@/lib/auth";
import { APP_NAME, getRoleHome } from "@/lib/constants";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/faq", label: "FAQ" },
];

const FOOTER_NAV_LINKS = [
  { label: "Home", href: "/" },
  { label: "About", href: "/about" },
  { label: "FAQ", href: "/faq" },
  { label: "Login", href: "/login" },
  { label: "Create account", href: "/signup" },
];

export function PublicLayout({
  children,
  redirectIfAuthenticated = true,
}: {
  children: ReactNode;
  redirectIfAuthenticated?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (redirectIfAuthenticated && !isLoading && user) {
      router.replace(getRoleHome(user.role));
    }
  }, [redirectIfAuthenticated, isLoading, user, router]);

  if (redirectIfAuthenticated && user) {
    return <BrandLoader fullScreen label="Redirecting…" />;
  }

  return (
    <div className="flex min-h-screen flex-col overflow-x-clip bg-bg text-text">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-30 h-16 border-b border-[#D1D5DB] bg-bg shadow-[0_1px_4px_rgba(17,24,39,0.08)]">
        <div className="mx-auto flex h-full max-w-app items-center justify-between px-4 sm:px-6">
          <Link href="/" aria-label={`${APP_NAME} home`}>
            <Logo />
          </Link>

          <nav aria-label="Main navigation" className="hidden items-center gap-8 sm:flex">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex h-16 items-center border-b-2 text-sm font-medium transition-colors ${
                    active
                      ? "border-accent text-accent"
                      : "border-transparent text-text-muted hover:text-text"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="hidden items-center gap-3 sm:flex">
            <Link
              href="/signup"
              className="inline-flex h-10 items-center justify-center rounded border border-border bg-bg px-4 text-sm font-medium text-text hover:bg-bg-subtle"
            >
              Create account
            </Link>
            <Link
              href="/login"
              className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Login
            </Link>
          </div>

          <button
            type="button"
            aria-label="Toggle navigation menu"
            aria-controls="public-mobile-nav"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="inline-flex h-10 w-10 items-center justify-center rounded text-text hover:bg-bg-subtle sm:hidden"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {menuOpen && (
          <nav
            id="public-mobile-nav"
            aria-label="Mobile navigation"
            className="border-b border-border bg-bg px-4 pb-4 pt-2 shadow-sm sm:hidden"
          >
            <div className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={`rounded px-3 py-2.5 text-sm font-medium ${
                      active ? "bg-accent-tint text-accent" : "text-text hover:bg-bg-subtle"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Link
                  href="/signup"
                  onClick={() => setMenuOpen(false)}
                  className="inline-flex h-10 items-center justify-center rounded border border-border bg-bg px-3 text-sm font-medium text-text hover:bg-bg-subtle"
                >
                  Create account
                </Link>
                <Link
                  href="/login"
                  onClick={() => setMenuOpen(false)}
                  className="inline-flex h-10 items-center justify-center rounded bg-accent px-3 text-sm font-medium text-white hover:bg-accent-hover"
                >
                  Login
                </Link>
              </div>
            </div>
          </nav>
        )}
      </header>

      <main id="main-content" className="flex-1">
        {children}
      </main>

      <Footer
        brandName={APP_NAME}
        brandHref="/"
        brandDescription="Privacy-first AI for medical documents. Personal details are removed, double-checked, and approved by you before any AI request."
        contactEmail="abdullahshahriar2140@gmail.com"
        navLinks={FOOTER_NAV_LINKS}
        rightNotice="Demo environment — use synthetic data only"
        disclaimerNotice="Documentation support tool. Not a medical device. Clinician review required."
        brandIconContainerClassName="bg-gradient-to-br from-bg to-accent-tint border border-border/80"
        brandIcon={
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src="/logo.png"
            alt={`${APP_NAME} logo`}
            className="h-9 sm:h-12 md:h-16 w-auto object-contain drop-shadow-sm"
          />
        }
      />
    </div>
  );
}
