"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, LoaderCircle, Save } from "lucide-react";
import { changePassword, resetPassword } from "@/lib/passwords";

export default function PasswordForm({ token, change = false }: { token?: string; change?: boolean }) {
  const router = useRouter();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmationError, setConfirmationError] = useState("");
  const [success, setSuccess] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || (!change && !token)) return;
    const element = event.currentTarget;
    const form = new FormData(element);
    const newPassword = String(form.get("new_password") ?? "");
    const confirmation = String(form.get("confirmation") ?? "");
    setError("");
    setConfirmationError("");
    setSuccess(false);
    if (newPassword !== confirmation) {
      setConfirmationError("La nueva contraseña y su confirmación no coinciden.");
      return;
    }
    if (Array.from(newPassword).length < 8 || new TextEncoder().encode(newPassword).length > 72) {
      setError("La nueva contraseña debe tener al menos 8 caracteres y no superar 72 bytes.");
      return;
    }
    pending.current = true;
    setBusy(true);
    try {
      if (change) {
        await changePassword(String(form.get("current_password") ?? ""), newPassword);
        element.reset();
        setSuccess(true);
      } else {
        await resetPassword(token!, newPassword);
        router.replace("/login?passwordReset=success");
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "No se pudo actualizar la contraseña.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  if (!change && !token) return <><p className="error-message" role="alert"><AlertCircle size={18} />El enlace de recuperación no contiene un token válido.</p><p className="auth-switch"><Link href="/forgot-password">Solicitar otro enlace</Link></p></>;

  return <form className="login-form" onSubmit={submit} aria-busy={busy}>
    <fieldset className="form-fields" disabled={busy}>
      {change && <label htmlFor="current-password">Contraseña actual<input id="current-password" name="current_password" type="password" autoComplete="current-password" required /></label>}
      <label htmlFor="new-password">Nueva contraseña<input id="new-password" name="new_password" type="password" autoComplete="new-password" minLength={8} required /></label>
      <label htmlFor="password-confirmation">Confirmar nueva contraseña<input id="password-confirmation" name="confirmation" type="password" autoComplete="new-password" required aria-invalid={Boolean(confirmationError)} aria-describedby={confirmationError ? "confirmation-error" : undefined} onChange={() => setConfirmationError("")} />{confirmationError && <span className="field-error" id="confirmation-error" role="alert">{confirmationError}</span>}</label>
    </fieldset>
    {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}
    {success && <p className="success-message" role="status"><CheckCircle2 size={18} />Contraseña actualizada correctamente.</p>}
    <button className="primary-button login-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle size={18} className="spinning" /> : <Save size={18} />}{busy ? "Guardando..." : "Guardar contraseña"}</button>
    {!change && <p className="auth-switch"><Link href="/forgot-password">Solicitar otro enlace de recuperación</Link></p>}
  </form>;
}