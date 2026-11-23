"use client";

import { useState, useEffect, type FormEvent } from "react";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

type TicketStatus = {
  ticket_id: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
  rfp_id: string | null;
};

type TicketList = { tickets: TicketStatus[] };

type DepartmentInfo = {
  department_id: string;
  department_name: string;
  key_aspects: Record<string, unknown>;
  approval_status: string;
};

type EvaluationResultType = {
  overall_pass: boolean;
  department_id: string;
  readability: { pass_: boolean; score: number | null; details: string };
  relevance: { pass_: boolean; missing_aspects: string[]; details: string };
  compliance: { pass_: boolean; rule_ids: string[]; violations: string[]; details: string };
  feedback_for_generator: string;
};

type DraftDeptInfo = {
  department_id: string;
  department_name: string;
  draft_content: string | null;
  key_aspects: Record<string, unknown>;
  approval_status: string;
  needs_human_review: boolean;
  iteration_count: number;
  evaluation_result: EvaluationResultType | null;
};

export default function RFPPage() {
  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [lastUploadId, setLastUploadId] = useState("");

  // Polling state
  const [pollId, setPollId] = useState("");
  const [ticket, setTicket] = useState<TicketStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [pollError, setPollError] = useState("");

  // Department state (Part 1)
  const [departments, setDepartments] = useState<Record<string, DepartmentInfo> | null>(null);
  const [loadingDepts, setLoadingDepts] = useState(false);
  const [deptError, setDeptError] = useState("");

  // Part 2 state (generation + drafts)
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, DraftDeptInfo> | null>(null);
  const [loadingDrafts, setLoadingDrafts] = useState(false);
  const [draftsError, setDraftsError] = useState("");

  // List state
  const [recentTickets, setRecentTickets] = useState<TicketStatus[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploading) return;

    const form = event.currentTarget;
    const fileInput = form.querySelector<HTMLInputElement>('input[type="file"]');
    if (!fileInput?.files?.[0]) {
      setUploadError("Selecciona un archivo PDF.");
      return;
    }

    const token = getStoredAccessToken();
    if (!token) {
      setUploadError("Inicia sesión para continuar.");
      return;
    }

    setUploading(true);
    setUploadError("");
    setLastUploadId("");

    try {
      const body = new FormData();
      body.append("file", fileInput.files[0]);

      const response = await fetch("/api/rfp/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });
      const payload = await response.json().catch(() => ({}));

      if (response.status === 401 || response.status === 403) {
        clearStoredAccessToken();
        window.dispatchEvent(new Event("nexova:unauthorized"));
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudo subir el archivo."
        );
      }
      if (typeof payload.ticket_id !== "string") {
        throw new Error("El servicio respondió sin un identificador de ticket.");
      }

      setLastUploadId(payload.ticket_id);
      setPollId(payload.ticket_id);
      void pollTicket(payload.ticket_id);
      form.reset();
    } catch (caught) {
      setUploadError(
        caught instanceof Error
          ? caught.message
          : "Error de conexión al subir el archivo."
      );
    } finally {
      setUploading(false);
    }
  }

  async function pollTicket(id: string) {
    const token = getStoredAccessToken();
    if (!token) return;

    setPolling(true);
    setPollError("");

    try {
      const response = await fetch(`/api/rfp/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));

      if (response.status === 401 || response.status === 403) {
        clearStoredAccessToken();
        window.dispatchEvent(new Event("nexova:unauthorized"));
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudo obtener el estado del ticket."
        );
      }
      setTicket(payload as TicketStatus);

      // If completed (Part 1), load departments
      if (payload.status === "analisis_completo") {
        void loadDepartments(id);
      } else if (payload.status === "descartado") {
        // Terminal state; stop polling
      } else if (
        payload.status === "generando_borrador" ||
        payload.status === "en_evaluacion"
      ) {
        // Part 2 in progress; load drafts and continue polling
        void loadDrafts(id);
        setTimeout(() => void pollTicket(id), 3000);
      } else if (
        payload.status === "needs_human_review"
      ) {
        // Terminal state for Part 2; load drafts for display
        void loadDrafts(id);
      } else {
        // Still processing (Part 1); poll again in 3s
        setTimeout(() => void pollTicket(id), 3000);
      }
    } catch (caught) {
      setPollError(
        caught instanceof Error ? caught.message : "Error al consultar el estado."
      );
    } finally {
      setPolling(false);
    }
  }

  async function loadDepartments(id: string) {
    const token = getStoredAccessToken();
    if (!token) return;

    setLoadingDepts(true);
    setDeptError("");

    try {
      const response = await fetch(`/api/rfp/${id}/departments`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudieron cargar los departamentos."
        );
      }
      setDepartments(payload.departments as Record<string, DepartmentInfo>);
    } catch (caught) {
      setDeptError(
        caught instanceof Error ? caught.message : "Error al cargar departamentos."
      );
    } finally {
      setLoadingDepts(false);
    }
  }

  async function handleGenerate() {
    if (!pollId || generating) return;

    const token = getStoredAccessToken();
    if (!token) {
      setGenError("Inicia sesión para continuar.");
      return;
    }

    setGenerating(true);
    setGenError("");

    try {
      const response = await fetch(`/api/rfp/${pollId}/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));

      if (response.status === 401 || response.status === 403) {
        clearStoredAccessToken();
        window.dispatchEvent(new Event("nexova:unauthorized"));
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudo iniciar la generación."
        );
      }

      // Start polling to see status transitions
      void pollTicket(pollId);
    } catch (caught) {
      setGenError(
        caught instanceof Error ? caught.message : "Error al iniciar generación."
      );
    } finally {
      setGenerating(false);
    }
  }

  async function loadDrafts(id: string) {
    const token = getStoredAccessToken();
    if (!token) return;

    setLoadingDrafts(true);
    setDraftsError("");

    try {
      const response = await fetch(`/api/rfp/${id}/drafts`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudieron cargar los borradores."
        );
      }
      setDrafts(payload.departments as Record<string, DraftDeptInfo>);
    } catch (caught) {
      setDraftsError(
        caught instanceof Error ? caught.message : "Error al cargar borradores."
      );
    } finally {
      setLoadingDrafts(false);
    }
  }

  async function loadRecentTickets() {
    const token = getStoredAccessToken();
    if (!token) return;

    setLoadingList(true);
    try {
      const response = await fetch("/api/rfp", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const payload = (await response.json()) as TicketList;
        setRecentTickets(payload.tickets ?? []);
      }
    } catch {
      // Silently fail; list is non-critical
    } finally {
      setLoadingList(false);
    }
  }

  function statusLabel(status: string): string {
    const labels: Record<string, string> = {
      analizando: "Analizando…",
      descartado: "Descartado",
      analisis_completo: "Análisis completo",
      generando_borrador: "Generando borrador",
      en_evaluacion: "En evaluación",
      needs_human_review: "Requiere revisión",
      esperando_aprobacion: "Esperando aprobación",
      terminado: "Terminado",
    };
    return labels[status] ?? status;
  }

  function statusClass(status: string): string {
    if (status === "analisis_completo" || status === "terminado") return "status-ok";
    if (status === "descartado") return "status-err";
    if (status === "analizando" || status === "generando_borrador" || status === "en_evaluacion") return "status-pending";
    if (status === "needs_human_review") return "status-warn";
    return "";
  }

  function evalIcon(pass: boolean | undefined): string {
    if (pass === undefined) return "⏳";
    return pass ? "✅" : "❌";
  }

  // Load recent tickets on page load
  useEffect(() => {
    void loadRecentTickets();
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <p className="badge">Nexova · Recepción de RFPs</p>
        <h1>Carga y análisis de solicitudes de propuesta</h1>
        <p>
          Sube una RFP en PDF para que el sistema la clasifique, extraiga los
          metadatos y distribuya el análisis a los departamentos correspondientes.
        </p>
      </section>

      {/* Upload form */}
      <section className="panel">
        <h2>Subir RFP</h2>
        <form onSubmit={handleUpload} aria-busy={uploading}>
          <label htmlFor="rfp-file">
            Archivo PDF
            <input
              id="rfp-file"
              type="file"
              accept=".pdf,application/pdf"
              required
              disabled={uploading}
            />
          </label>
          <button className="btn btn-dark" type="submit" disabled={uploading}>
            {uploading ? "Subiendo y analizando…" : "Subir RFP"}
          </button>
        </form>

        {uploadError && (
          <div className="notice notice-error" role="alert">
            {uploadError}
          </div>
        )}

        {lastUploadId && (
          <div className="notice notice-info" role="status">
            Ticket creado: <strong>{lastUploadId}</strong>
          </div>
        )}
      </section>

      {/* Polling / current ticket status */}
      {pollId && (
        <section className="panel" aria-live="polite">
          <h2>Estado del ticket</h2>
          {ticket && (
            <div>
              <p>
                <strong>ID:</strong> {ticket.ticket_id}
              </p>
              <p>
                <strong>Estado:</strong>{" "}
                <span className={statusClass(ticket.status)}>
                  {statusLabel(ticket.status)}
                </span>
              </p>
              {ticket.rfp_id && (
                <p>
                  <strong>RFP ID:</strong> {ticket.rfp_id}
                </p>
              )}
              {ticket.error_message && (
                <div className="notice notice-error" role="alert">
                  {ticket.error_message}
                </div>
              )}
            </div>
          )}
          {polling && <p className="status-pending">Consultando estado…</p>}
          {pollError && (
            <div className="notice notice-error" role="alert">
              {pollError}
            </div>
          )}

          {/* Department cards */}
          {ticket?.status === "analisis_completo" && (
            <div>
              <h3>Análisis por departamento</h3>
              {loadingDepts && <p>Cargando departamentos…</p>}
              {deptError && (
                <div className="notice notice-error" role="alert">
                  {deptError}
                </div>
              )}
              {departments &&
                Object.entries(departments).map(([deptId, info]) => (
                  <article className="dept-card" key={deptId}>
                    <h4>{info.department_name ?? deptId}</h4>
                    <p>
                      <strong>Estado:</strong> {info.approval_status}
                    </p>
                    {!!info.key_aspects?.roles_to_cover && (
                      <p>
                        <strong>Roles:</strong>{" "}
                        {(info.key_aspects.roles_to_cover as string[]).join(", ")}
                      </p>
                    )}
                    {info.key_aspects?.agent_count != null && (
                      <p>
                        <strong>Agentes:</strong> {String(info.key_aspects.agent_count)}
                      </p>
                    )}
                    {!!info.key_aspects?.applicable_programs && (
                      <p>
                        <strong>Programas:</strong>{" "}
                        {(info.key_aspects.applicable_programs as string[]).join(", ")}
                      </p>
                    )}
                    {!!info.key_aspects?.open_questions && (
                      <details>
                        <summary>Preguntas pendientes</summary>
                        <ul>
                          {(info.key_aspects.open_questions as string[]).map(
                            (q: string) => <li key={q}>{q}</li>
                          )}
                        </ul>
                      </details>
                    )}
                  </article>
                ))}
              <div className="hero-actions" style={{ marginTop: "1rem" }}>
                <button
                  className="btn btn-dark"
                  onClick={handleGenerate}
                  disabled={generating}
                >
                  {generating ? "Generando propuesta…" : "Generar propuesta"}
                </button>
              </div>
              {genError && (
                <div className="notice notice-error" role="alert">
                  {genError}
                </div>
              )}
            </div>
          )}

          {/* Drafts (Part 2) */}
          {(ticket?.status === "generando_borrador" ||
            ticket?.status === "en_evaluacion" ||
            ticket?.status === "needs_human_review") && (
            <div>
              <h3>Borradores generados</h3>
              {loadingDrafts && <p className="status-pending">Cargando borradores…</p>}
              {draftsError && (
                <div className="notice notice-error" role="alert">
                  {draftsError}
                </div>
              )}
              {drafts &&
                Object.entries(drafts).map(([deptId, info]) => (
                  <article
                    className="dept-card"
                    key={deptId}
                    style={{
                      borderLeft: info.needs_human_review
                        ? "4px solid #d97706"
                        : info.evaluation_result?.overall_pass
                        ? "4px solid #14745d"
                        : "4px solid #dc2626",
                    }}
                  >
                    <h4>
                      {info.department_name ?? deptId}
                      {info.needs_human_review && (
                        <span
                          className="status-badge status-warn-badge"
                          style={{
                            marginLeft: "0.5rem",
                            fontSize: "0.7rem",
                            background: "#fef3c7",
                            color: "#92400e",
                            padding: "0.15rem 0.45rem",
                            borderRadius: "999px",
                          }}
                        >
                          Revisión humana
                        </span>
                      )}
                    </h4>
                    <p>
                      <strong>Iteración:</strong> {info.iteration_count}
                    </p>
                    {info.draft_content && (
                      <details>
                        <summary>Ver borrador</summary>
                        <pre
                          style={{
                            whiteSpace: "pre-wrap",
                            background: "#f9fafb",
                            padding: "0.75rem",
                            borderRadius: "0.5rem",
                            fontSize: "0.85rem",
                            maxHeight: "400px",
                            overflow: "auto",
                            border: "1px solid #e5e7eb",
                          }}
                        >
                          {info.draft_content}
                        </pre>
                      </details>
                    )}
                    {info.evaluation_result && (
                      <details>
                        <summary>
                          Evaluación{" "}
                          {info.evaluation_result.overall_pass ? "✅" : "❌"}
                        </summary>
                        <div
                          style={{
                            marginTop: "0.5rem",
                            display: "grid",
                            gap: "0.5rem",
                          }}
                        >
                          <div>
                            <strong>Legibilidad:</strong>{" "}
                            {evalIcon(info.evaluation_result.readability?.pass_)}
                            {info.evaluation_result.readability?.score != null &&
                              ` (puntuación: ${info.evaluation_result.readability.score})`}
                            {info.evaluation_result.readability?.details && (
                              <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                                {info.evaluation_result.readability.details}
                              </p>
                            )}
                          </div>
                          <div>
                            <strong>Pertinencia:</strong>{" "}
                            {evalIcon(info.evaluation_result.relevance?.pass_)}
                            {info.evaluation_result.relevance?.missing_aspects
                              ?.length > 0 && (
                              <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                                Aspectos faltantes:{" "}
                                {info.evaluation_result.relevance.missing_aspects.join(
                                  ", "
                                )}
                              </p>
                            )}
                            {info.evaluation_result.relevance?.details && (
                              <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                                {info.evaluation_result.relevance.details}
                              </p>
                            )}
                          </div>
                          <div>
                            <strong>Cumplimiento:</strong>{" "}
                            {evalIcon(info.evaluation_result.compliance?.pass_)}
                            {info.evaluation_result.compliance?.violations
                              ?.length > 0 && (
                              <p style={{ fontSize: "0.8rem", color: "#dc2626" }}>
                                Violaciones:{" "}
                                {info.evaluation_result.compliance.violations.join(
                                  "; "
                                )}
                              </p>
                            )}
                            {info.evaluation_result.compliance?.details && (
                              <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                                {info.evaluation_result.compliance.details}
                              </p>
                            )}
                          </div>
                          {info.evaluation_result.feedback_for_generator && (
                            <div
                              className="notice notice-info"
                              style={{ fontSize: "0.85rem" }}
                            >
                              <strong>Feedback:</strong>{" "}
                              {info.evaluation_result.feedback_for_generator}
                            </div>
                          )}
                        </div>
                      </details>
                    )}
                  </article>
                ))}
            </div>
          )}
        </section>
      )}

      {/* Recent tickets */}
      <section className="panel">
        <h2>Tickets recientes</h2>
        {loadingList && <p>Cargando…</p>}
        {recentTickets.length === 0 && !loadingList && (
          <p className="empty-state">No hay tickets aún. Sube una RFP para comenzar.</p>
        )}
        {recentTickets.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Estado</th>
                <th>RFP ID</th>
                <th>Creado</th>
              </tr>
            </thead>
            <tbody>
              {recentTickets.map((t) => (
                <tr key={t.ticket_id}>
                  <td>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        setPollId(t.ticket_id);
                        void pollTicket(t.ticket_id);
                      }}
                    >
                      {t.ticket_id.substring(0, 8)}…
                    </a>
                  </td>
                  <td>
                    <span className={statusClass(t.status)}>
                      {statusLabel(t.status)}
                    </span>
                  </td>
                  <td>
                    {t.rfp_id ? t.rfp_id.substring(0, 8) + "…" : "—"}
                  </td>
                  <td>
                    {t.created_at
                      ? new Date(t.created_at).toLocaleString("es-ES")
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}