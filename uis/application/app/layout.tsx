import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { Building2, UserRound } from "lucide-react";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "./globals.css";
import SessionGuard from "./session-guard";

export const metadata: Metadata = {
  title: "Proveedores | Nexova",
  description: "Directorio de proveedores de Nexova.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <SessionGuard>
        <header className="app-header">
          <Link className="brand" href="/">nexova<span>OPERACIONES</span></Link>
          <nav aria-label="Menu de la aplicacion">
            <Link href="/suppliers"><Building2 size={18} /> Proveedores</Link>
            <Link href="/account/profile"><UserRound size={18} /> Mi cuenta</Link>
          </nav>
          <span className="workspace-name">Valencia / Miami</span>
        </header>
        <main>{children}</main>
        </SessionGuard>
      </body>
    </html>
  );
}