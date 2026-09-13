import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";
import contextVariants from "@oods/tw-variants";
import path from "node:path";

const tokenColor = (name: string) => `color-mix(in srgb, var(--theme-${name}) calc(<alpha-value> * 100%), transparent)`;

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        background: tokenColor("surface-canvas"),
        surface: tokenColor("surface-raised"),
        "surface-alt": tokenColor("surface-subtle"),
        card: tokenColor("surface-raised"),
        foreground: tokenColor("text-primary"),
        secondary: tokenColor("text-secondary"),
        muted: tokenColor("text-muted"),
        line: tokenColor("border-subtle"),
        "line-strong": tokenColor("border-strong"),
        accent: tokenColor("surface-interactive-primary-default"),
        "accent-strong": tokenColor("surface-interactive-primary-hover"),
        "accent-text": tokenColor("text-accent"),
        "on-accent": tokenColor("text-on-interactive"),
        inverse: tokenColor("surface-inverse"),
        "on-inverse": tokenColor("text-inverse"),
        backdrop: tokenColor("surface-backdrop"),
        focus: tokenColor("focus-ring-outer"),
        info: tokenColor("status-info-text"),
        "info-surface": tokenColor("status-info-surface"),
        "info-line": tokenColor("status-info-border"),
        danger: tokenColor("status-critical-text"),
        "danger-surface": tokenColor("status-critical-surface"),
        "danger-line": tokenColor("status-critical-border"),
        success: tokenColor("status-success-text"),
        "success-surface": tokenColor("status-success-surface"),
        "success-line": tokenColor("status-success-border"),
        warning: tokenColor("status-warning-text"),
        "warning-surface": tokenColor("status-warning-surface"),
        "warning-line": tokenColor("status-warning-border"),
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [
    typography,
    contextVariants({ tokensPath: path.join(__dirname, "node_modules/@oods/tokens/dist/tailwind/tokens.json") }),
  ],
};

export default config;
