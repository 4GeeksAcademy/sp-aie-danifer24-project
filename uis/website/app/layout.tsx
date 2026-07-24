import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nexova | Consultoria de Talento",
  description:
    "Consultora de recursos humanos y adquisicion de talento para empresas de tecnologia, retail y servicios financieros.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
