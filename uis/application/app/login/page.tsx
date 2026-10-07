"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { loginRequest, storeAccessToken } from "@/lib/auth";

export default function LoginPage() {
  return <Suspense fallback={<p className="notice" role="status">Cargando...</p>}><LoginForm /></Suspense>;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    setBusy(true);
    setError("");

    try {
      storeAccessToken(await loginRequest(email, password));
      router.replace("/suppliers");
    } catch (error) {
      setError(error instanceof Error ? error.message : "No se pudo iniciar sesión. Inténtalo de nuevo.");
      setBusy(false);
    }
  }

  return (
    <section className="login-page">
      <div className="login-panel">
        <div className="login-mark" aria-hidden="true"><LockKeyhole size={20} /></div>
        <div className="login-heading">
          <div className="eyebrow">ACCESO AL ESPACIO DE TRABAJO</div>
          <h1>Inicia sesión</h1>
          <p className="page-subtitle">Accede a las operaciones de Nexova.</p>
        </div>

        <form className="login-form" onSubmit={submit}>
          {searchParams.get("passwordReset") === "success" && <p className="success-message" role="status">Contraseña restablecida. Ya puedes iniciar sesión.</p>}
          <fieldset className="form-fields" disabled={busy}>
            <label htmlFor="login-email">Correo electrónico
              <input id="login-email" name="email" type="email" autoComplete="email" required autoFocus />
            </label>
            <label htmlFor="login-password">Contraseña
              <input id="login-password" name="password" type="password" autoComplete="current-password" required />
            </label>
          </fieldset>

          {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}

          <button className="primary-button login-submit" type="submit" disabled={busy}>
            {busy ? <LoaderCircle size={18} className="spinning" /> : <ArrowRight size={18} />}
            {busy ? "Verificando acceso…" : "Entrar"}
          </button>
        </form>
        <p className="auth-switch"><Link href="/forgot-password">¿Olvidaste tu contraseña?</Link></p>
        <p className="auth-switch">¿No tienes una cuenta? <Link href="/register">Regístrate</Link></p>
      </div>
    </section>
  );
}