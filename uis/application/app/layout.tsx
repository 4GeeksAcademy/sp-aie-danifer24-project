import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { Building2 } from "lucide-react";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Proveedores | Nexova",
  description: "Directorio de proveedores de Nexova.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="app-header">
          <Link className="brand" href="/">nexova<span>OPERACIONES</span></Link>
          <nav aria-label="Menu de la aplicacion">
            <Link href="/suppliers" aria-current="page"><Building2 size={18} /> Proveedores</Link>
          </nav>
          <span className="workspace-name">Valencia / Miami</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}