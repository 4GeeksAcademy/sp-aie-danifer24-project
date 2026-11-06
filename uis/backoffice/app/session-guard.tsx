"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSessionToken, InvalidSessionError, validateSession } from "../../../packages/shared/auth/session";
import { track } from "@/lib/telemetry";

export default function SessionGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (["/login", "/register", "/forgot-password", "/reset-password"].includes(pathname)) return children;
  return <ProtectedSession key={pathname}>{children}</ProtectedSession>;
}

function ProtectedSession({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [result, setResult] = useState<{ error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const trackedView = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let generation = 0;
    function trackAuthorizedView() {
      if (trackedView.current) return;
      trackedView.current = true;
      const section = pathname === "/" ? "home" :
        pathname === "/inventory/products" ? "inventory_products" :
        pathname === "/inventory/orders/inbound" ? "inventory_inbound" :
        pathname === "/inventory/orders/outbound" ? "inventory_outbound" :
        pathname === "/inventory/orders" ? "inventory_orders" :
        pathname === "/suppliers" ? "suppliers" :
        pathname === "/incidents" ? "incidents" :
        pathname === "/incidents/new" ? "incident_new" :
        pathname === "/reporting" ? "reporting" :
        pathname === "/account/profile" ? "account_profile" :
        pathname.startsWith("/account/") ? "account_password" :
        pathname === "/validacion-tecnica" ? "technical_validation" : "unknown";
      track("backoffice_section_viewed", { section, entry_type: "unknown" });
    }
    function rejectSession() {
      generation += 1;
      setResult(null);
      router.replace("/login");
    }
    async function checkSession() {
      const current = ++generation;
      try {
        await validateSession(controller.signal);
        if (!controller.signal.aborted && current === generation) {
          trackAuthorizedView();
          setResult({ error: "" });
        }
      } catch (error) {
        if (controller.signal.aborted || current !== generation) return;
        if (error instanceof InvalidSessionError) rejectSession();
        else setResult({ error: error instanceof Error ? error.message : "No se pudo verificar tu sesión." });
      }
    }
    function refreshSession() {
      setResult(null);
      void checkSession();
    }
    void checkSession();
    window.addEventListener("nexova:unauthorized", rejectSession);
    window.addEventListener("storage", refreshSession);
    window.addEventListener("focus", refreshSession);
    const timer = window.setInterval(() => { void checkSession(); }, 60000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("nexova:unauthorized", rejectSession);
      window.removeEventListener("storage", refreshSession);
      window.removeEventListener("focus", refreshSession);
    };
  }, [router, attempt, pathname]);

  if (!result) return (
    <main className="session-verifying" role="status" aria-live="polite" aria-label="Verificando sesión">
      <section className="session-verifying-card">
        <span className="session-verifying-spinner" aria-hidden="true" />
        <div>
          <strong>Comprobando tu acceso</strong>
          <p>Un momento, estamos preparando tu espacio de trabajo.</p>
        </div>
      </section>
    </main>
  );
  if (result.error) return <main className="auth-page"><p role="alert">{result.error}</p><button onClick={() => { setResult(null); setAttempt((current) => current + 1); }}>Reintentar</button></main>;
  return <><div className="session-actions"><button type="button" onClick={() => { clearSessionToken(); router.replace("/login"); }}>Cerrar sesión</button></div>{children}</>;
}