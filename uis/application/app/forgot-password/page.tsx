"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, LoaderCircle, Mail } from "lucide-react";
import { forgotPassword } from "@/lib/passwords";

export default function ForgotPasswordPage() {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || sent) return;
    const email = String(new FormData(event.currentTarget).get("email") ?? "").trim();
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (error) {
      setError(error instanceof Error ? error.message : "No se pudo enviar la solicitud.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <section className="login-page"><div className="login-panel">
    <div className="login-mark" aria-hidden="true"><Mail size={20} /></div>
    <div className="login-heading"><h1>Recuperar contraseña</h1></div>
    <form className="login-form" onSubmit={submit} aria-busy={busy}>
      <fieldset className="form-fields" disabled={busy || sent}>
        <label htmlFor="forgot-email">Correo electrónico<input id="forgot-email" name="email" type="email" autoComplete="email" required /></label>
        <button className={sent ? "primary-button login-submit request-sent" : "primary-button login-submit"} type="submit" disabled={busy || sent}>{sent ? <CheckCircle2 size={18} /> : busy ? <LoaderCircle size={18} className="spinning" /> : <Mail size={18} />}{sent ? "Solicitud enviada" : busy ? "Enviando..." : "Enviar enlace"}</button>
      </fieldset>
      {sent && <p className="success-message" role="status"><CheckCircle2 size={18} />Si esa dirección está registrada, recibirás un enlace en breve.</p>}
      {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}
    </form>
    <p className="auth-switch"><Link href="/login">Volver a iniciar sesión</Link></p>
  </div></section>;
}