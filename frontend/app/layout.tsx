import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import { RouteProgressBar } from "@/components/ui/RouteProgressBar";
import { ToastContainer } from "@/components/ui/Toast";
import { AppProviders } from "@/lib/auth";
import { APP_NAME } from "@/lib/constants";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0F766E",
};

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} — Privacy-First AI for Clinical Documents`,
    template: `%s | ${APP_NAME}`,
  },
  description:
    "De-identify patient PDFs and medical photos automatically with HIPAA-18 safeguards, review every change side-by-side, generate clinical drafts safely with AI, and restore real details only on your screen.",
  applicationName: APP_NAME,
  keywords: [
    "clinical AI",
    "HIPAA de-identification",
    "medical document privacy",
    "discharge summary",
    "PHI redaction",
    "healthcare AI gateway",
  ],
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/logo.png", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/logo.png",
  },
  openGraph: {
    title: `${APP_NAME} — Privacy-First AI for Clinical Documents`,
    description:
      "Hide personal patient details before any AI request and restore them only on your screen.",
    type: "website",
    siteName: APP_NAME,
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} overflow-x-clip`}>
      <body className="min-h-screen overflow-x-clip bg-bg font-sans text-text antialiased">
        <AppProviders>
          <RouteProgressBar />
          {children}
          <ToastContainer />
        </AppProviders>
      </body>
    </html>
  );
}
