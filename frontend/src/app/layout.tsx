import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegBot | Global Alliance for Genomics and Health",
  description:
    "A citation-oriented regulatory navigation workspace for genomic and health data policy.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
