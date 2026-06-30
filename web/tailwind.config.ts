import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171717",
        paper: "#fbfcfb",
        civic: "#0f766e",
        line: "#d8dedb",
        muted: "#64706b"
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"]
      },
      boxShadow: {
        soft: "0 18px 60px rgba(26, 23, 18, 0.10)"
      }
    }
  },
  plugins: []
};

export default config;
