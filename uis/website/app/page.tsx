import Link from "next/link";

const schemaOrg = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Nexova",
  description: "Consultora de recursos humanos y adquisicion de talento",
  url: "https://nexova.com",
  foundingDate: "2011",
  address: [
    {
      "@type": "PostalAddress",
      addressCountry: "ES",
      addressLocality: "Valencia",
      addressRegion: "Comunidad Valenciana",
    },
    {
      "@type": "PostalAddress",
      addressCountry: "US",
      addressLocality: "Miami",
      addressRegion: "Florida",
    },
  ],
  contactPoint: {
    "@type": "ContactPoint",
    telephone: "+34-960-123-456",
    contactType: "customer service",
    availableLanguage: ["Spanish", "English"],
  },
  sameAs: [
    "https://linkedin.com/company/nexova",
    "https://instagram.com/nexova",
  ],
};

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaOrg) }}
      />
      <a className="skip-link" href="#contenido">
        Saltar al contenido principal
      </a>

      <header className="header" id="inicio">
        <div className="container header-inner">
          <p className="brand">Nexova</p>
          <nav aria-label="Navegacion principal" className="nav-main">
            <a href="#inicio">Inicio</a>
            <a href="#servicios">Servicios</a>
            <a href="#talento">Talento</a>
            <a href="#contacto">Contacto</a>
          </nav>
        </div>
      </header>

      <main className="container" id="contenido">
        <section className="hero">
          <h1>Construimos equipos excepcionales para empresas en crecimiento</h1>
          <p>
            Consultora de recursos humanos y adquisicion de talento con mas de
            10 anos ayudando a empresas de tecnologia, retail y servicios
            financieros a encontrar y desarrollar el mejor talento.
          </p>
          <Link className="button-primary" href="/talento">
            Unete a nuestro banco de talento
          </Link>
        </section>

        <section className="section" id="servicios" aria-labelledby="servicios-title">
          <h2 id="servicios-title">Servicios</h2>
          <div className="grid-3">
            <article className="card">
              <h3>Headhunting Ejecutivo</h3>
              <ul>
                <li>Busqueda y seleccion de perfiles ejecutivos y mandos medios</li>
                <li>Proceso personalizado con garantia de reemplazo</li>
              </ul>
            </article>

            <article className="card">
              <h3>Outsourcing de Atencion al Cliente</h3>
              <ul>
                <li>Equipos especializados para empresas tecnologicas</li>
                <li>Formacion continua y supervision dedicada</li>
              </ul>
            </article>

            <article className="card">
              <h3>Formacion Corporativa</h3>
              <ul>
                <li>Programas de soft skills y liderazgo</li>
                <li>Cursos presenciales y en linea adaptados a cada organizacion</li>
              </ul>
            </article>
          </div>
        </section>

        <section className="section" aria-labelledby="porque-title">
          <h2 id="porque-title">Por que Nexova</h2>
          <div className="grid-2">
            <article className="card">
              <h3>12 anos de experiencia</h3>
              <p>en el mercado latinoamericano</p>
            </article>
            <article className="card">
              <h3>Presencia regional</h3>
              <p>Espana y Estados Unidos</p>
            </article>
            <article className="card">
              <h3>+500 procesos exitosos</h3>
              <p>de seleccion completados</p>
            </article>
            <article className="card">
              <h3>Especializacion sectorial</h3>
              <p>tecnologia, retail y finanzas</p>
            </article>
          </div>
        </section>

        <section className="section" id="talento" aria-labelledby="talento-title">
          <h2 id="talento-title">Banco de Talento</h2>
          <p>
            Eres profesional y quieres postularte a oportunidades actuales o
            futuras en Nexova.
          </p>
          <Link className="button-primary" href="/talento">
            Ir al formulario de registro
          </Link>
          <p className="note">
            Eres una empresa buscando talento? Escribenos a contacto@nexova.com
          </p>
        </section>

        <section className="section" id="contacto" aria-labelledby="contacto-title">
          <h2 id="contacto-title">Contacto</h2>
          <ul className="contact-list">
            <li>Email: contacto@nexova.com</li>
            <li>Valencia: +34 960 123 456</li>
            <li>Miami: +1 305 555 0191</li>
          </ul>
        </section>
      </main>

      <footer className="footer">
        <div className="container footer-inner">
          <p>© 2025 Nexova. Todos los derechos reservados.</p>
          <p>LinkedIn | Instagram</p>
        </div>
      </footer>
    </>
  );
}
