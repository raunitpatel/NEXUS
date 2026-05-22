import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["SF Mono", "Fira Code", "monospace"],
      },
      colors: {
        nexus: {
          // Core accent
          accent: "#534AB7",
          "accent-hover": "#4840A0",
          // Semantic
          success: "#1D9E75",
          warning: "#BA7517",
          error: "#E24B4A",
          // Surfaces
          sidebar: "#1C1C1A",
          card: "#FFFFFF",
          bg: "#F5F4F0",
          // Text
          dark: "#1C1C1A",
          body: "#2C2C2A",
          muted: "#888780",
          subtle: "#B0AFA9",
          // Agent colors
          "search-bg": "#E6F1FB",
          "search-text": "#0C447C",
          "search-dot": "#378ADD",
          "code-bg": "#FAEEDA",
          "code-text": "#633806",
          "code-dot": "#EF9F27",
          "memory-bg": "#EEEDFE",
          "memory-text": "#3C3489",
          "memory-dot": "#7F77DD",
          "tool-bg": "#E1F5EE",
          "tool-text": "#085041",
          "tool-dot": "#1D9E75",
        },
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "7px",
        lg: "8px",
        xl: "10px",
      },
    },
  },
  plugins: [],
};

export default config;
