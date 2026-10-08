"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  BRANCH_LABELS,
  CATEGORY_LABELS,
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  ORIGIN_LABELS,
  STATUS_LABELS,
  createIncident,
  type IncidentBranch,
  type IncidentCategory,
  type IncidentOrigin,
  type IncidentStatus,
} from "../../../lib/incidents";

const FIELD_LABELS: Record<string, string> = {
  title: "Título",
  description: "Descripción",
  category: "Categoría",
  status: "Estado",
  origin: "Origen",
  branch: "Sede",
};

export default function NewIncidentPage() {
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [origin, setOrigin] = useState<IncidentOrigin | "">("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setSuccess("");
    setError("");
    setFieldErrors({});
    try {
      await createIncident({
        title: String(values.get("title") ?? "").trim(),
        description: String(values.get("description") ?? "").trim(),
        category: String(values.get("category")) as IncidentCategory,
        status: String(values.get("status")) as IncidentStatus,
        origin: String(values.get("origin")) as IncidentOrigin,
        branch: String(values.get("branch")) as IncidentBranch,
      });
      form.reset();
      setOrigin("");
      setSuccess("La incidencia se ha registrado correctamente.");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "No se pudo registrar la incidencia. Inténtalo de nuevo.";
      const field = caught && typeof caught === "object" && "field" in caught
        ? (caught as { field?: unknown }).field
        : undefined;
      if (typeof field === "string" && FIELD_LABELS[field]) setFieldErrors({ [field]: message });
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell incidents-shell">
      <section className="hero">
        <p className="badge">Nexova · Incidencias</p>
        <h1>Registrar incidencia</h1>
        <p>Registra un problema para que el equipo pueda darle seguimiento.</p>
        <div className="hero-actions"><Link className="btn btn-outline" href="/incidents">Volver al panel</Link></div>
      </section>

      <section className="incident-panel form-panel">
        {success && <p className="notice notice-success" role="status">{success}</p>}
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        <form className="incident-form" onSubmit={submit} aria-busy={busy}>
          <fieldset disabled={busy}>
            <label htmlFor="title">Título
              <input id="title" name="title" maxLength={200} required aria-invalid={Boolean(fieldErrors.title)} aria-describedby={fieldErrors.title ? "title-error" : undefined} />
              {fieldErrors.title && <span className="field-error" id="title-error">{fieldErrors.title}</span>}
            </label>
            <label htmlFor="description">Descripción
              <textarea id="description" name="description" rows={5} required aria-invalid={Boolean(fieldErrors.description)} aria-describedby={fieldErrors.description ? "description-error" : undefined} />
              {fieldErrors.description && <span className="field-error" id="description-error">{fieldErrors.description}</span>}
            </label>
            <div className="form-columns">
              <label htmlFor="category">Categoría
                <select id="category" name="category" required defaultValue="" aria-invalid={Boolean(fieldErrors.category)}>
                  <option value="" disabled>Selecciona una categoría</option>
                  {INCIDENT_CATEGORIES.map((value) => <option key={value} value={value}>{CATEGORY_LABELS[value]}</option>)}
                </select>
                {fieldErrors.category && <span className="field-error">{fieldErrors.category}</span>}
              </label>
              <label htmlFor="status">Estado
                <select id="status" name="status" required defaultValue="open" aria-invalid={Boolean(fieldErrors.status)}>
                  {INCIDENT_STATUSES.map((value) => <option key={value} value={value}>{STATUS_LABELS[value]}</option>)}
                </select>
                {fieldErrors.status && <span className="field-error">{fieldErrors.status}</span>}
              </label>
              <label htmlFor="origin">Origen
                <select id="origin" name="origin" required value={origin} onChange={(event) => setOrigin(event.target.value as IncidentOrigin | "")} aria-invalid={Boolean(fieldErrors.origin)}>
                  <option value="" disabled>Selecciona el origen</option>
                  {INCIDENT_ORIGINS.map((value) => <option key={value} value={value}>{ORIGIN_LABELS[value]}</option>)}
                </select>
                {fieldErrors.origin && <span className="field-error">{fieldErrors.origin}</span>}
              </label>
              <label className={`branch-field${origin === "branch" ? " branch-field-highlight" : ""}`} htmlFor="branch">
                Sede
                <select id="branch" name="branch" required defaultValue="central" aria-invalid={Boolean(fieldErrors.branch)} aria-describedby={origin === "branch" ? "branch-hint" : fieldErrors.branch ? "branch-error" : undefined}>
                  {INCIDENT_BRANCHES.map((value) => <option key={value} value={value}>{BRANCH_LABELS[value]}</option>)}
                </select>
                {origin === "branch" && <span className="field-hint" id="branch-hint">Selecciona la oficina desde la que se reporta.</span>}
                {fieldErrors.branch && <span className="field-error" id="branch-error">{fieldErrors.branch}</span>}
              </label>
            </div>
          </fieldset>
          <button className="btn btn-dark submit-button" type="submit" disabled={busy}>{busy ? <><span className="spinner" aria-hidden="true" /> Enviando incidencia…</> : "Registrar incidencia"}</button>
        </form>
      </section>
    </main>
  );
}
