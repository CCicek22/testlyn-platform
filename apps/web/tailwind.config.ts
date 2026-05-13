import type { Config } from "tailwindcss";

/**
 * Tailwind v4 config — theme tokens from CLAUDE.md §4 (FROZEN).
 * Colors, fonts, and dark-mode strategy are brand-level — do not change
 * without user approval.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Brand primary (indigo)
        primary: {
          DEFAULT: "#3730A3",
          50: "#ECEEFB",
          100: "#D0D2F6",
          200: "#A1A6ED",
          300: "#7179E4",
          400: "#504DDB",
          500: "#3730A3",
          600: "#2C2880",
          700: "#211F60",
          800: "#161540",
          900: "#0B0A20",
        },
        // Semantic
        success: "#10B981",
        warn: "#F59E0B",
        alert: "#EF4444",
        // Surfaces
        dark: "#0A0A0B",
        light: "#FAFAFA",
        // Product accents (sidebar stays indigo; these are for chart strokes / header bars)
        "accent-load": "#3730A3",
        // Reserved for Phase 2+:
        // 'accent-functional': '#8B5CF6',
        // 'accent-a11y': '#14B8A6',
        // 'accent-synthetic': '#F59E0B',
        // 'accent-contract': '#06B6D4',
        // 'accent-security': '#DC2626',
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        // Cal Sans — geometric sans for marketing hero (with fallback)
        display: ["Cal Sans", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
