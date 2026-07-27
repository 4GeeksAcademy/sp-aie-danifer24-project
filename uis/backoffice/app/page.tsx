import Link from "next/link";

export default function HomePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="badge">Backoffice · Nexova</p>
        <h1>Panel Interno</h1>
        <p>
          Vista de entrada del backoffice para operaciones internas. Desde aqui
          puedes navegar a los modulos de trabajo y a la vista de validacion.
        </p>
      </section>

      <section className="playground-grid" aria-label="Accesos de backoffice">
        <article className="panel">
          <div className="panel-header">
            <h2>Accesos rapidos</h2>
          </div>
          <p>
            Usa este espacio como estructura base de dashboard. Puedes conectar
            aqui widgets de pipeline, actividad y alertas.
          </p>
          <p>
            <Link className="btn btn-dark" href="/validacion-tecnica">
              Abrir centro de validacion tecnica
            </Link>
          </p>
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Resumen operativo</h2>
          </div>
          <ul>
            <li>Dashboard base disponible en la ruta /</li>
            <li>Centro de validacion disponible en /validacion-tecnica</li>
            <li>Logica de negocio importada desde src/utils y src/types</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
