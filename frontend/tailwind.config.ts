import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#FFFFFF",
        "bg-subtle": "#F7F8F9",
        border: "#E5E7EB",
        text: "#111827",
        "text-muted": "#6B7280",
        accent: "#0F766E",
        "accent-hover": "#0D5F59",
        "accent-tint": "#E6F4F1",
        danger: "#B91C1C",
        "danger-tint": "#FEF2F2",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "6px",
        modal: "8px",
      },
      boxShadow: {
        modal: "0 8px 24px rgba(0,0,0,.12)",
      },
      maxWidth: {
        app: "1120px",
        prose: "720px",
        form: "640px",
      },
    },
  },
  plugins: [],
};

export default config;
