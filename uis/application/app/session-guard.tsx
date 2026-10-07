"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { InvalidSessionError, validateSession } from "../../../packages/shared/auth/session";

export default function SessionGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (["/login", "/register", "/forgot-password", "/reset-password"].includes(pathname)) return children;
  return <ProtectedSession key={pathname}>{children}</ProtectedSession>;
}

function ProtectedSession({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [result, setResult] = useState<{ error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let generation = 0;

    function rejectSession() {
      generation += 1;
      setResult(null);
      router.replace("/login");
    }

    async function checkSession() {
      const current = ++generation;
      try {
        await validateSession(controller.signal);
        if (!controller.signal.aborted && current === generation) setResult({ error: "" });
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
  }, [router, attempt]);

  if (!result) return <main><p role="status">Verificando sesión...</p></main>;
  if (result.error) return <main><p role="alert">{result.error}</p><button className="secondary-button" onClick={() => { setResult(null); setAttempt((current) => current + 1); }}>Reintentar</button></main>;
  return children;
}