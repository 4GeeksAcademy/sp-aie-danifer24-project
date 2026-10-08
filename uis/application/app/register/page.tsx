"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, LoaderCircle, UserRoundPlus } from "lucide-react";
import {
  loginRequest,
  RegistrationError,
  registerRequest,
  storeAccessToken,
  type RegistrationField,
  type RegistrationFieldErrors,
  type RegistrationInput,
} from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<RegistrationFieldErrors>({});

  function clearFieldError(field: RegistrationField) {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const input: RegistrationInput = {
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
    };
    for (const field of ["name", "phone", "address"] as const) {
      const value = String(form.get(field) ?? "").trim();
      if (value) input[field] = value;
    }

    setBusy(true);
    setError("");
    setFieldErrors({});
    let accountCreated = false;
    try {
      await registerRequest(input);
      accountCreated = true;
      storeAccessToken(await loginRequest(input.email, input.password));
      router.replace("/suppliers");
    } catch (error) {
      if (error instanceof RegistrationError) {
        setFieldErrors(error.fieldErrors);
      } else if (accountCreated) {
        setError("La cuenta se creó, pero no se pudo iniciar sesión automáticamente. Ya puedes entrar con tus credenciales.");
      } else {
        setError(error instanceof Error ? error.message : "No se pudo crear la cuenta. Inténtalo de nuevo.");
      }
    } finally {
      setBusy(false);
    }
  }

  function fieldError(field: RegistrationField) {
    const message = fieldErrors[field];
    return message ? <span className="field-error" id={`register-${field}-error`}>{message}</span> : null;
  }

  return (
    <section className="login-page register-page">
      <div className="login-panel">
        <div className="login-mark" aria-hidden="true"><UserRoundPlus size={20} /></div>
        <div className="login-heading">
          <div className="eyebrow">NUEVA CUENTA</div>
          <h1>Crear cuenta</h1>
          <p className="page-subtitle">Regístrate para acceder a las operaciones de Nexova.</p>
        </div>

        <form className="register-form" onSubmit={submit} noValidate>
          <fieldset className="register-fields" disabled={busy}>
            <label htmlFor="register-name">Nombre <span className="optional-label">Opcional</span>
              <input id="register-name" name="name" autoComplete="name" aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? "register-name-error" : undefined} onChange={() => clearFieldError("name")} />
              {fieldError("name")}
            </label>
            <label htmlFor="register-phone">Teléfono <span className="optional-label">Opcional</span>
              <input id="register-phone" name="phone" type="tel" autoComplete="tel" aria-invalid={Boolean(fieldErrors.phone)} aria-describedby={fieldErrors.phone ? "register-phone-error" : undefined} onChange={() => clearFieldError("phone")} />
              {fieldError("phone")}
            </label>
            <label className="register-full-width" htmlFor="register-address">Dirección <span className="optional-label">Opcional</span>
              <input id="register-address" name="address" autoComplete="street-address" aria-invalid={Boolean(fieldErrors.address)} aria-describedby={fieldErrors.address ? "register-address-error" : undefined} onChange={() => clearFieldError("address")} />
              {fieldError("address")}
            </label>
            <label htmlFor="register-email">Correo electrónico
              <input id="register-email" name="email" type="email" autoComplete="email" required aria-invalid={Boolean(fieldErrors.email)} aria-describedby={fieldErrors.email ? "register-email-error" : undefined} onChange={() => clearFieldError("email")} />
              {fieldError("email")}
            </label>
            <label htmlFor="register-password">Contraseña
              <input id="register-password" name="password" type="password" autoComplete="new-password" minLength={8} required aria-invalid={Boolean(fieldErrors.password)} aria-describedby={fieldErrors.password ? "register-password-error" : undefined} onChange={() => clearFieldError("password")} />
              {fieldError("password")}
            </label>
          </fieldset>

          {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}

          <button className="primary-button login-submit" type="submit" disabled={busy}>
            {busy ? <LoaderCircle size={18} className="spinning" /> : <ArrowRight size={18} />}
            {busy ? "Creando cuenta…" : "Crear cuenta"}
          </button>
        </form>

        <p className="auth-switch">¿Ya tienes una cuenta? <Link href="/login">Inicia sesión</Link></p>
      </div>
    </section>
  );
}