/** @type {import('next').NextConfig} */
const PAGE_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://accounts.google.com",
  "style-src 'self' 'unsafe-inline' https://accounts.google.com",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self' https://accounts.google.com blob:",
  "frame-src 'self' https://accounts.google.com blob:",
  "object-src 'self' blob:",
  "media-src 'self' blob:",
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

// Auth pages (/login, /signup) host Google Identity Services (GSI), which requires
// origin referrer for Authorized JavaScript Origin checks, COOP allow-popups for
// credential postMessage, and Google asset origins in img-src / form-action.
const AUTH_PAGE_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://accounts.google.com",
  "style-src 'self' 'unsafe-inline' https://accounts.google.com",
  "img-src 'self' data: blob: https://accounts.google.com https://*.googleusercontent.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  "connect-src 'self' https://accounts.google.com blob:",
  "frame-src 'self' https://accounts.google.com blob:",
  "object-src 'self' blob:",
  "media-src 'self' blob:",
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "form-action 'self' https://accounts.google.com",
].join("; ");

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/((?!api/).*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
          { key: "Content-Security-Policy", value: PAGE_CSP },
        ],
      },
      {
        source: "/(login|signup)",
        headers: [
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
          { key: "Content-Security-Policy", value: AUTH_PAGE_CSP },
        ],
      },
    ];
  },
  async rewrites() {
    const backendUrl = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
