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
  const hasSessionCookie =
    Boolean(request.cookies.get("access_token")?.value) ||
    Boolean(request.cookies.get("refresh_token")?.value);

  if (hasSessionCookie && PUBLIC_ONLY_PATHS.has(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (!hasSessionCookie && isProtected) {
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
