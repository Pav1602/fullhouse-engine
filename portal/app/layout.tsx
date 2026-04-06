import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fullhouse Portal",
  description: "Participant portal — Fullhouse Hackathon, 1 June 2026",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0a0a]">{children}</body>
    </html>
  );
}
