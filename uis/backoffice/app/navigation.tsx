"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function BackofficeNavigation() {
  const pathname = usePathname();
  if (pathname === "/login") return null;
  return (
    <nav className="app-nav" aria-label="Menú principal">
      <Link className="app-nav-brand" href="/">Nexova <span>Operaciones</span></Link>
      <div className="app-nav-links">
        <Link href="/incidents" aria-current={pathname === "/incidents" ? "page" : undefined}>Incidencias</Link>
        <Link href="/incidents/new" aria-current={pathname === "/incidents/new" ? "page" : undefined}>Registrar incidencia</Link>
        <Link href="/validacion-tecnica" aria-current={pathname === "/validacion-tecnica" ? "page" : undefined}>Validación técnica</Link>
      </div>
    </nav>
  );
}
