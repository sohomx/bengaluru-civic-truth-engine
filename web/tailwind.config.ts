import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171717",
        paper: "#f7f4ef",
        civic: "#0f766e",
        line: "#ded8cc",
        muted: "#6f6a61"
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
