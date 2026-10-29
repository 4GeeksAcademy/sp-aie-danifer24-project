import Link from "next/link";
import { ArrowRight, Boxes, Building2, ClipboardList, FlaskConical } from "lucide-react";

export default function HomePage() {
  return (
    <main className="shell backoffice-home">
      <section className="hero backoffice-home-hero">
        <p className="badge">Operaciones · Nexova</p>
        <h1>Centro de operaciones</h1>
        <p>Un espacio para gestionar proveedores, inventario e incidencias de los equipos de Valencia y Miami.</p>
      </section>

      <section className="backoffice-home-section" aria-labelledby="operations-heading">
        <div className="backoffice-section-heading">
          <p className="eyebrow">ÁREAS DE TRABAJO</p>
          <h2 id="operations-heading">Gestión operativa</h2>
        </div>
        <div className="backoffice-home-grid" aria-label="Accesos de backoffice">
          <Link className="panel backoffice-home-card" href="/suppliers">
            <span className="backoffice-home-icon"><Building2 size={21} /></span>
            <span className="backoffice-home-card-copy"><strong>Proveedores</strong><span>Directorio, tarifas, renovaciones y estado de contratos.</span></span>
            <span className="backoffice-home-card-action">Abrir directorio <ArrowRight size={16} /></span>
          </Link>
          <Link className="panel backoffice-home-card" href="/inventory/products">
            <span className="backoffice-home-icon"><Boxes size={21} /></span>
            <span className="backoffice-home-card-copy"><strong>Inventario</strong><span>Productos, niveles de stock, entradas y salidas.</span></span>
            <span className="backoffice-home-card-action">Ver inventario <ArrowRight size={16} /></span>
          </Link>
          <Link className="panel backoffice-home-card" href="/incidents">
            <span className="backoffice-home-icon"><ClipboardList size={21} /></span>
            <span className="backoffice-home-card-copy"><strong>Incidencias</strong><span>Registro, seguimiento de estados y métricas del equipo.</span></span>
            <span className="backoffice-home-card-action">Ver incidencias <ArrowRight size={16} /></span>
          </Link>
          <Link className="panel backoffice-home-card" href="/validacion-tecnica">
            <span className="backoffice-home-icon"><FlaskConical size={21} /></span>
            <span className="backoffice-home-card-copy"><strong>Validación técnica</strong><span>Herramientas para ejecutar comprobaciones y revisar resultados.</span></span>
            <span className="backoffice-home-card-action">Abrir herramientas <ArrowRight size={16} /></span>
          </Link>
        </div>
      </section>

      <nav className="backoffice-home-shortcuts" aria-label="Accesos rápidos">
        <Link href="/incidents/new">Registrar incidencia <ArrowRight size={15} /></Link>
        <Link href="/inventory/orders">Consultar pedidos <ArrowRight size={15} /></Link>
        <Link href="/account/profile">Mi cuenta <ArrowRight size={15} /></Link>
      </nav>
    </main>
  );
}
