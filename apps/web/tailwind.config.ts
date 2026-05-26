import type { Config } from "tailwindcss";

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
        primary: {
          DEFAULT: "#18F2C3",
          50: "#E8FFF9",
          100: "#B9FFF0",
          200: "#7CFFE1",
          300: "#47FBD2",
          400: "#18F2C3",
          500: "#18F2C3",
          600: "#08B99D",
          700: "#077F75",
          800: "#064F4C",
          900: "#032B2E",
        },
        success: "#5CFF93",
        warn: "#FFD166",
        alert: "#FF4D6D",
        dark: "#05090B",
        light: "#071115",
        "accent-load": "#18F2C3",
        "accent-functional": "#7CFFE1",
        "accent-a11y": "#5CFF93",
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
