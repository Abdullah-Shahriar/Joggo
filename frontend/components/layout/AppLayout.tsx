"use client";

import { ChevronDown, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { BrandLoader } from "@/components/ui/BrandLoader";
import { ForbiddenView } from "@/components/ui/ForbiddenView";
import { Logo } from "@/components/ui/Logo";
import { Footer } from "@/components/ui/modem-animated-footer";
import { useAuth } from "@/lib/auth";
import { APP_NAME, getRoleHome, type UserRole } from "@/lib/constants";

interface NavItem {
  href: string;
  label: string;
}

const ROLE_MENUS: Record<UserRole, NavItem[]> = {
  doctor: [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/documents/new", label: "New document" },
    { href: "/documents", label: "My documents" },
    { href: "/help", label: "Help" },
  ],
  admin: [
    { href: "/admin", label: "Overview" },
    { href: "/admin/users", label: "Users" },
    { href: "/admin/complaints", label: "Complaints" },
    { href: "/admin/audit", label: "Audit logs" },
    { href: "/admin/analytics", label: "Analytics" },
  ],
  auditor: [
    { href: "/admin/audit", label: "Audit logs" },
    { href: "/help", label: "Help" },
  ],
};

export function AppLayout({
  children,
  allowedRoles,
  preFooter,
  bottomPaddingClass = "",
}: {
  children: ReactNode;
  allowedRoles?: UserRole[];
  preFooter?: ReactNode;
  bottomPaddingClass?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      const next = encodeURIComponent(pathname || "/dashboard");
      router.replace(`/login?next=${next}`);
    }
  }, [isLoading, user, pathname, router]);

  useEffect(() => {
    if (!isLoading && user && pathname === "/dashboard" && user.role !== "doctor") {
      router.replace(getRoleHome(user.role));
    }
  }, [isLoading, user, pathname, router]);

  useEffect(() => {
    setMenuOpen(false);
    setProfileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (isLoading || !user) {
    return <BrandLoader fullScreen label="Loading…" />;
  }

  // If middleware sent an admin or auditor to /dashboard from a public route, show loader while effect redirects
  if (pathname === "/dashboard" && user.role !== "doctor") {
    return <BrandLoader fullScreen label="Redirecting…" />;
  }

  const isAllowed = !allowedRoles || allowedRoles.includes(user.role);
  const navItems = ROLE_MENUS[user.role];
  const roleHome = getRoleHome(user.role);

  const footerQuickLinks = [
    ...navItems.map((item) => ({ label: item.label, href: item.href })),
    { label: "Profile", href: "/profile" },
  ];

  const handleSignOut = async () => {
    setProfileOpen(false);
    setMenuOpen(false);
    await logout();
    router.replace("/");
  };

  return (
    <div className={`flex min-h-screen flex-col overflow-x-clip bg-bg text-text ${bottomPaddingClass}`}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-30 h-16 border-b border-[#D1D5DB] bg-bg shadow-[0_1px_4px_rgba(17,24,39,0.08)]">
        <div className="mx-auto flex h-full max-w-app items-center justify-between px-4 sm:px-6">
          <Link href={roleHome} aria-label={`${APP_NAME} home`}>
            <Logo />
          </Link>

          <nav aria-label="Application navigation" className="hidden items-center gap-6 lg:flex">
            {navItems.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/admin" &&
                  item.href !== "/documents" &&
                  pathname.startsWith(`${item.href}/`)) ||
                (item.href === "/documents" &&
                  pathname.startsWith("/documents/") &&
                  pathname !== "/documents/new");
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

          <div className="flex items-center gap-2">
            <div ref={profileRef} className="relative">
              <button
                type="button"
                aria-expanded={profileOpen}
                aria-haspopup="menu"
                onClick={() => setProfileOpen((v) => !v)}
                className="inline-flex h-10 items-center gap-2 rounded px-2.5 text-sm font-medium text-text hover:bg-bg-subtle"
              >
                {user.avatar_data_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={user.avatar_data_url}
                    alt=""
                    className="h-7 w-7 rounded-full border border-border object-cover"
                  />
                ) : (
                  <span
                    aria-hidden="true"
                    className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent"
                  >
                    {user.full_name
                      .split(" ")
                      .map((part) => part[0])
                      .join("")
                      .slice(0, 2)
                      .toUpperCase()}
                  </span>
                )}
                <span className="hidden max-w-[140px] truncate sm:inline">{user.full_name}</span>
                <ChevronDown className="h-4 w-4 text-text-muted" />
              </button>

              {profileOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-1 w-44 rounded border border-border bg-bg py-1 shadow-modal"
                >
                  <Link
                    role="menuitem"
                    href="/profile"
                    onClick={() => setProfileOpen(false)}
                    className="block px-3 py-2 text-sm text-text hover:bg-bg-subtle"
                  >
                    Profile
                  </Link>
                  <button
                    role="menuitem"
                    type="button"
                    onClick={handleSignOut}
                    className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-bg-subtle"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="app-mobile-nav"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
              className="inline-flex h-10 w-10 items-center justify-center rounded text-text hover:bg-bg-subtle lg:hidden"
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav
            id="app-mobile-nav"
            aria-label="Mobile navigation"
            className="border-b border-border bg-bg px-4 pb-4 pt-2 shadow-sm lg:hidden"
          >
            <div className="flex flex-col gap-1">
              {navItems.map((item) => {
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
              <div className="my-1 border-t border-border" />
              <Link
                href="/profile"
                onClick={() => setMenuOpen(false)}
                className={`rounded px-3 py-2.5 text-sm font-medium ${
                  pathname === "/profile" ? "bg-accent-tint text-accent" : "text-text hover:bg-bg-subtle"
                }`}
              >
                Profile
              </Link>
              <button
                type="button"
                onClick={handleSignOut}
                className="rounded px-3 py-2.5 text-left text-sm font-medium text-danger hover:bg-danger-tint"
              >
                Sign out
              </button>
            </div>
          </nav>
        )}
      </header>

      <main id="main-content" className="mx-auto w-full max-w-app flex-1 px-4 py-8 sm:px-6">
        {isAllowed ? children : <ForbiddenView />}
      </main>

      {isAllowed && preFooter ? (
        <div className="mt-6 w-full border-t border-border bg-bg-subtle/70">{preFooter}</div>
      ) : null}

      <Footer
        brandName={APP_NAME}
        brandHref={roleHome}
        brandDescription="Privacy-first AI for medical documents. Personal details are removed, double-checked, and approved by you before any AI request."
        contactEmail="abdullahshahriar2140@gmail.com"
        navLinks={footerQuickLinks}
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
