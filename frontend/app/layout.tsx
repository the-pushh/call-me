import type { Metadata } from "next";
import { DM_Sans, Instrument_Serif } from "next/font/google";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

// Serif voice for the AI side of the transcript — visually distinct from the
// user's DM Sans without splitting the column. Instrument Serif ships weight 400.
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Call Me",
  description: "Call Me — reach anyone, anywhere",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${dmSans.variable} ${instrumentSerif.variable} h-full antialiased`}>
      <body className={`${dmSans.className} min-h-full flex flex-col`}>{children}</body>
    </html>
  );
}
