import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bengaluru Civic Truth Engine",
  description: "Public-safe civic action packets for Bengaluru issues."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
