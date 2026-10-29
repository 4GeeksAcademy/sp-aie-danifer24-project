import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import SessionGuard from "./session-guard";
import BackofficeNavigation from "./navigation";

export const metadata: Metadata = {
  title: "Nexova | Centro de operaciones",
  description: "Operaciones internas de Nexova: proveedores, inventario e incidencias.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body><SessionGuard><BackofficeNavigation />{children}</SessionGuard></body>
    </html>
  );
}
