import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bengaluru Civic Truth Engine",
  description: "Official-record civic dossiers for Bengaluru localities."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
