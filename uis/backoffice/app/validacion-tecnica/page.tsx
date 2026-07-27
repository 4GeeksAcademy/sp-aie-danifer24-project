import Link from "next/link";
import { TestingPlayground } from "@/components/TestingPlayground";

export default function TechnicalValidationPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="badge">Backoffice · Nexova</p>
        <h1>Centro de Validacion Tecnica</h1>
        <p>
          Espacio de validacion funcional para filtros, busquedas, scoring,
          reportes y reglas de negocio.
        </p>
        <div className="hero-actions">
          <Link className="btn btn-outline" href="/">
            Volver al inicio
          </Link>
        </div>
      </section>

      <TestingPlayground />
    </main>
  );
}