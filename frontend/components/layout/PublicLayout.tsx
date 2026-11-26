"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BrandLoader } from "@/components/ui/BrandLoader";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/lib/auth";
import { APP_NAME, getRoleHome } from "@/lib/constants";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/faq", label: "FAQ" },
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
    if (redirectIfAuthenticated && !isLoading && user) {
      router.replace(getRoleHome(user.role));
    }
  }, [redirectIfAuthenticated, isLoading, user, router]);

  if (redirectIfAuthenticated && user) {
    return <BrandLoader fullScreen label="Redirecting…" />;
  }

  const year = new Date().getFullYear();

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-30 h-16 border-b border-border bg-bg">
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

          <div className="hidden sm:block">
            <Link
              href="/login"
              className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Login
            </Link>
          </div>

          <button
            type="button"
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="inline-flex h-10 w-10 items-center justify-center rounded text-text hover:bg-bg-subtle sm:hidden"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {menuOpen && (
          <nav
            aria-label="Mobile navigation"
            className="border-b border-border bg-bg px-4 pb-4 pt-2 sm:hidden"
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
              <Link
                href="/login"
                onClick={() => setMenuOpen(false)}
                className="mt-2 inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
              >
                Login
              </Link>
            </div>
          </nav>
        )}
      </header>

      <main id="main-content" className="flex-1">
        {children}
      </main>

      <footer className="border-t border-border bg-bg py-8">
        <div className="mx-auto max-w-app px-4 sm:px-6">
          <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-center">
            <div>
              <Logo />
              <p className="mt-1.5 text-xs text-text-muted">
                Privacy-first AI for clinical documents.
              </p>
            </div>

            <nav aria-label="Footer navigation" className="flex items-center gap-6 text-sm text-text-muted">
              {NAV_ITEMS.map((item) => (
                <Link key={item.href} href={item.href} className="hover:text-text">
                  {item.label}
                </Link>
              ))}
            </nav>

            <p className="text-xs text-text-muted">Demo environment — synthetic data only</p>
          </div>
          <div className="mt-6 border-t border-border pt-4 text-xs text-text-muted">
            © {year} {APP_NAME}
          </div>
        </div>
      </footer>
    </div>
  );
}
