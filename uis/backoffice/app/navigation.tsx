"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function BackofficeNavigation() {
  const pathname = usePathname();
  if (["/login", "/register", "/forgot-password", "/reset-password"].includes(pathname)) return null;
  return (
    <nav className="app-nav" aria-label="Menú principal">
      <Link className="app-nav-brand" href="/">Nexova <span>Operaciones</span></Link>
      <div className="app-nav-links">
        <Link href="/suppliers" aria-current={pathname.startsWith("/suppliers") ? "page" : undefined}>Proveedores</Link>
        <Link href="/inventory/products" aria-current={pathname.startsWith("/inventory") ? "page" : undefined}>Inventario</Link>
        <Link href="/incidents" aria-current={pathname === "/incidents" ? "page" : undefined}>Incidencias</Link>
        <Link href="/validacion-tecnica" aria-current={pathname === "/validacion-tecnica" ? "page" : undefined}>Validación técnica</Link>
        <Link href="/account/profile" aria-current={pathname.startsWith("/account") ? "page" : undefined}>Mi cuenta</Link>
      </div>
    </nav>
  );
}
