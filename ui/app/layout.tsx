import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MMFP — Model Fitness Platform",
  description: "Morae Model Fitness Platform scorecard viewer",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-neutral-1 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
