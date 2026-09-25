import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "prismjs/themes/prism-okaidia.css";
import "./globals.css";
import { SessionProvider } from "@/lib/session";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WP Dev Agent",
  description:
    "GitHub-based AI development agent for WordPress and Elementor repositories.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
