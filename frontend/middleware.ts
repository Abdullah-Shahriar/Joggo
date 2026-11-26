import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_ONLY_PATHS = new Set([
  "/",
  "/about",
  "/faq",
  "/login",
  "/signup",
  "/00admin/00admin",
  "/00auditor",
]);
const PROTECTED_PREFIXES = ["/dashboard", "/documents", "/help", "/profile", "/admin"];

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasAccessToken = Boolean(request.cookies.get("access_token")?.value);
  const hasSessionHint = request.cookies.get("joggo_session")?.value === "1";

  // Public-only routes: redirect away ONLY when access_token exists so a stale
  // joggo_session hint cookie can never cause a /login <-> /dashboard loop.
  if (hasAccessToken && PUBLIC_ONLY_PATHS.has(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Protected routes: treat session as present if access_token OR joggo_session=1
  // exists; AppLayout verifies with /api/me, which silently refreshes once on 401.
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (!hasAccessToken && !hasSessionHint && isProtected) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/about",
    "/faq",
    "/login",
    "/signup",
    "/00admin/00admin",
    "/00auditor",
    "/dashboard/:path*",
    "/documents/:path*",
    "/help/:path*",
    "/profile/:path*",
    "/admin/:path*",
  ],
};
