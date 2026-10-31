import { TalentForm } from "@/components/TalentForm";
import { SiteHeader } from "../../components/SiteHeader";

export default function TalentPage() {
  return (
    <>
      <SiteHeader navigationLabel="Navegacion secundaria" />

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
