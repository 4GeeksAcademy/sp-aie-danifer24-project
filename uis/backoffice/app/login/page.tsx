"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "../../../../packages/shared/auth/session";

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await signIn(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
      router.replace("/");
    } catch (error) {
      setError(error instanceof Error ? error.message : "No se pudo iniciar sesión.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <h1>Nexova</h1><h2>Inicia sesión</h2>
      <form className="auth-form" onSubmit={submit} aria-busy={busy}>
        <fieldset disabled={busy}>
          <label htmlFor="email">Correo electrónico<input id="email" name="email" type="email" autoComplete="email" required /></label>
          <label htmlFor="password">Contraseña<input id="password" name="password" type="password" autoComplete="current-password" required /></label>
        </fieldset>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Verificando acceso..." : "Entrar"}</button>
      </form>
    </main>
  );
}