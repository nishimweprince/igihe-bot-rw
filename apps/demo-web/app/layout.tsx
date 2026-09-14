import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin", "latin-ext"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "IGIHE News Assistant (demo)",
  description: "Kinyarwanda news assistant demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="rw">
      <body className={dmSans.className}>{children}</body>
    </html>
  );
}
