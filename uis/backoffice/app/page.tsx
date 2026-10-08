import Link from "next/link";

export default function HomePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="badge">Backoffice · Nexova</p>
        <h1>Panel Interno</h1>
        <p>
          Centro de operaciones de Nexova para dar seguimiento a incidencias y
          acceder a las herramientas del equipo.
        </p>
      </section>

      <section className="backoffice-home-grid" aria-label="Accesos de backoffice">
        <article className="panel">
          <div className="panel-header">
            <h2>Gestión de incidencias</h2>
          </div>
          <p>
            Consulta los problemas reportados, revisa sus métricas o registra
            una nueva incidencia para el equipo.
          </p>
          <div className="quick-links">
            <Link className="btn btn-dark" href="/incidents">Abrir panel de incidencias</Link>
            <Link className="btn btn-outline" href="/incidents/new">Registrar incidencia</Link>
          </div>
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Resumen operativo</h2>
          </div>
          <ul>
            <li>Incidencias de cliente, sedes y operaciones internas</li>
            <li>Seguimiento de estados y métricas agregadas</li>
            <li><Link href="/validacion-tecnica">Centro de validación técnica</Link></li>
          </ul>
        </article>
      </section>
    </main>
  );
}
