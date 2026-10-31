import Link from "next/link";

type SiteHeaderProps = {
  navigationLabel: string;
  showHomeLink?: boolean;
};

export function SiteHeader({ navigationLabel, showHomeLink = false }: SiteHeaderProps) {
  return (
    <header className="header" id={showHomeLink ? "inicio" : undefined}>
      <div className="container header-inner">
        <p className="brand">Nexova</p>
        <nav aria-label={navigationLabel} className="nav-main">
          {showHomeLink ? (
            <>
              <a href="#inicio">Inicio</a>
              <a href="#servicios">Servicios</a>
              <a href="#talento">Talento</a>
              <a href="#contacto">Contacto</a>
            </>
          ) : (
            <>
              <Link href="/">Inicio</Link>
              <a href="#formulario">Formulario</a>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}