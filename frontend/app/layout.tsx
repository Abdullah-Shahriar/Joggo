import type { Metadata } from "next";
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

export const metadata: Metadata = {
  title: APP_NAME,
  description: "Privacy-first AI for clinical documents.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-bg font-sans text-text antialiased">
        <AppProviders>
          <RouteProgressBar />
          {children}
          <ToastContainer />
        </AppProviders>
      </body>
    </html>
  );
}
