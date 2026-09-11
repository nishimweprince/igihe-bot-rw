import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IGIHE News Assistant (demo)",
  description: "Kinyarwanda news assistant demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="rw">
      <body>{children}</body>
    </html>
  );
}
