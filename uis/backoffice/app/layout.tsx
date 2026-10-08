import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import SessionGuard from "./session-guard";
import BackofficeNavigation from "./navigation";

export const metadata: Metadata = {
  title: "Nexova Backoffice | Panel Interno",
  description: "Backoffice interno con centro de validacion tecnica para funciones de negocio.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body><SessionGuard><BackofficeNavigation />{children}</SessionGuard></body>
    </html>
  );
}
