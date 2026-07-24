import Link from "next/link";
import { TalentForm } from "@/components/TalentForm";

export default function TalentPage() {
  return (
    <>
      <header className="header">
        <div className="container header-inner">
          <p className="brand">Nexova</p>
          <nav aria-label="Navegacion secundaria" className="nav-main">
            <Link href="/">Inicio</Link>
            <a href="#formulario">Formulario</a>
          </nav>
        </div>
      </header>

      <main className="container page-content" id="formulario">
        <section className="section">
          <h1>Registro de talento</h1>
          <p>
            Formulario para profesionales en busqueda activa o pasiva de
            oportunidades laborales.
          </p>
          <p className="note">
            Eres una empresa buscando talento? Escribenos a contacto@nexova.com
          </p>
          <TalentForm />
        </section>
      </main>
    </>
  );
}
