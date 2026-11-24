"use client";

import { useState, useEffect, useRef, type FormEvent } from "react";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

type TicketStatus = {
  ticket_id: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
  rfp_id: string | null;
};

type TicketList = { tickets: TicketStatus[]; total: number; page: number; page_size: number };

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
  const pollIdRef = useRef("");
  const [ticket, setTicket] = useState<TicketStatus | null>(null);
  const [pollError, setPollError] = useState("");
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Part 3: Approval state
  const [approveStarting, setApproveStarting] = useState(false);
  const [approveError, setApproveError] = useState("");
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [docError, setDocError] = useState("");
  const [finalDoc, setFinalDoc] = useState<{
    document_type?: string;
    generated_at?: string;
    content?: string;
  } | null>(null);

  // Ticket browser state
  const [recentTickets, setRecentTickets] = useState<TicketStatus[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [ticketSearch, setTicketSearch] = useState("");
  const [ticketTab, setTicketTab] = useState("todos");
  const [ticketDepartment, setTicketDepartment] = useState("");
  const [ticketPage, setTicketPage] = useState(1);
  const [ticketTotal, setTicketTotal] = useState(0);
  const ticketPageSize = 20;
  const ticketPageCount = Math.max(1, Math.ceil(ticketTotal / ticketPageSize));

  function setActiveTicket(id: string) {
    // Cancel any pending poll timer from previous ticket
    if (pollTimerRef.current !== null) clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    pollIdRef.current = id;
    setPollId(id);
    setTicket(null);
    setDrafts(null);
    setDepartments(null);
    setFinalDoc(null);
    setPollError("");
    setApproveError("");
  }

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
      setActiveTicket(payload.ticket_id);
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

      // Only update state if this ticket is still the active one
      if (pollIdRef.current !== id) return;
      setTicket(payload as TicketStatus);
      // Keep the visible ticket list in sync with the authoritative status response.
      setRecentTickets((current) =>
        current.map((item) =>
          item.ticket_id === id ? { ...item, ...payload } : item
        )
      );

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
        schedulePoll(id);
      } else if (
        payload.status === "needs_human_review"
      ) {
        // Terminal state for Part 2; load drafts for display
        void loadDrafts(id);
      } else if (
        payload.status === "esperando_aprobacion"
      ) {
        // Waiting for a human: load approval state once; refresh after a decision.
        void loadDrafts(id);
      } else if (
        payload.status === "terminado"
      ) {
        // Terminal state for Part 3; load final document
        void loadDrafts(id);
        void loadFinalDocument(id);
      } else {
        // Still processing (Part 1); poll again in 3s
        schedulePoll(id);
      }
    } catch (caught) {
      // Only set error if this ticket is still active
      if (pollIdRef.current === id) {
        setPollError(
          caught instanceof Error ? caught.message : "Error al consultar el estado."
        );
      }
    } finally {
    }
  }

  function schedulePoll(id: string) {
    if (pollTimerRef.current !== null) clearTimeout(pollTimerRef.current);
    pollTimerRef.current = setTimeout(() => {
      pollTimerRef.current = null;
      if (pollIdRef.current === id) {
        void pollTicket(id);
      }
    }, 3000);
  }

  useEffect(() => {
    return () => {
      if (pollTimerRef.current !== null) clearTimeout(pollTimerRef.current);
    };
  }, []);

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
      if (pollIdRef.current === id) {
        setDrafts(payload.departments as Record<string, DraftDeptInfo>);
        setLoadingDrafts(false);
      }
    } catch (caught) {
      setDraftsError(
        caught instanceof Error ? caught.message : "Error al cargar borradores."
      );
    } finally {
      setLoadingDrafts(false);
    }
  }

  async function handleStartApproval() {
    if (!pollId || approveStarting) return;

    const token = getStoredAccessToken();
    if (!token) {
      setApproveError("Inicia sesión para continuar.");
      return;
    }

    setApproveStarting(true);
    setApproveError("");

    try {
      const response = await fetch(`/api/rfp/${pollId}/approve`, {
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
            : "No se pudo iniciar la aprobación."
        );
      }

      // Start polling to catch status transitions
      void pollTicket(pollId);
    } catch (caught) {
      setApproveError(
        caught instanceof Error ? caught.message : "Error al iniciar aprobación."
      );
    } finally {
      setApproveStarting(false);
    }
  }

  async function handleResumeApproval(
    departmentId: string,
    action: string,
    feedback: string
  ) {
    const token = getStoredAccessToken();
    if (!token) {
      setApproveError("Inicia sesión para continuar.");
      return;
    }

    try {
      const response = await fetch(
        `/api/rfp/${pollId}/approve/${departmentId}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ action, feedback }),
        }
      );
      const payload = await response.json().catch(() => ({}));

      if (response.status === 401 || response.status === 403) {
        clearStoredAccessToken();
        window.dispatchEvent(new Event("nexova:unauthorized"));
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "Error al registrar aprobación."
        );
      }

      // Reload approval state immediately after the decision.
      await Promise.all([loadDrafts(pollId), pollTicket(pollId)]);
    } catch (caught) {
      setApproveError(
        caught instanceof Error
          ? caught.message
          : "Error al registrar aprobación."
      );
    }
  }

  async function loadFinalDocument(id: string) {
    const token = getStoredAccessToken();
    if (!token) return;

    setLoadingDoc(true);
    setDocError("");

    try {
      const response = await fetch(`/api/rfp/${id}/final-document`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status !== 404) {
          throw new Error(
            typeof payload.detail === "string"
              ? payload.detail
              : "No se pudo cargar el documento final."
          );
        }
        // 404 is expected if doc not yet available
        return;
      }
      setFinalDoc(payload as Record<string, unknown>);
    } catch (caught) {
      setDocError(
        caught instanceof Error
          ? caught.message
          : "Error al cargar documento final."
      );
    } finally {
      setLoadingDoc(false);
    }
  }

  async function loadRecentTickets() {
    const token = getStoredAccessToken();
    if (!token) return;

    setLoadingList(true);
    try {
      const params = new URLSearchParams({ page: String(ticketPage), page_size: String(ticketPageSize) });
      if (ticketSearch.trim()) params.set("search", ticketSearch.trim());
      const selectedTab = ticketTabs.find((tab) => tab.id === ticketTab);
      if (selectedTab?.statuses) params.set("status", selectedTab.statuses.join(","));
      if (ticketDepartment) params.set("department", ticketDepartment);
      const response = await fetch(`/api/rfp?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const payload = (await response.json()) as TicketList;
        setRecentTickets(payload.tickets ?? []);
        setTicketTotal(payload.total ?? 0);
      }
    } catch {
      // Silently fail; list is non-critical
    } finally {
      setLoadingList(false);
    }
  }

  const ticketTabs = [
    { id: "todos", label: "Todos" },
    { id: "activos", label: "En curso", statuses: ["analizando", "generando_borrador", "en_evaluacion"] },
    { id: "aprobacion", label: "Esperando aprobación", statuses: ["esperando_aprobacion", "needs_human_review"] },
    { id: "terminados", label: "Terminados", statuses: ["terminado"] },
  ];
  const visibleTickets = recentTickets;

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

  // Refresh the current server-side page when filters or pagination change.
  useEffect(() => {
    const timer = setTimeout(() => void loadRecentTickets(), ticketSearch ? 250 : 0);
    return () => clearTimeout(timer);
  }, [ticketPage, ticketSearch, ticketTab, ticketDepartment]);

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

          {ticket?.status === "needs_human_review" && (
            <div className="notice notice-info" role="status">
              <strong>Revisión humana necesaria.</strong> El límite de iteraciones se ha alcanzado para una o más secciones. Revisa la evaluación y el borrador de cada departamento; no equivale a una aprobación departamental.
            </div>
          )}
          {ticket?.status === "esperando_aprobacion" && (
            <div className="notice notice-info" role="status">
              <strong>Esperando aprobación departamental.</strong> Cada responsable debe dar su visto bueno antes de generar el documento final.
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

          {/* Part 3: Approval UI */}
          {(ticket?.status === "esperando_aprobacion" ||
            ticket?.status === "terminado") && (
            <div>
              <h3>Aprobación departamental</h3>
              {drafts &&
                Object.entries(drafts).map(([deptId, info]) => (
                  <article
                    className="dept-card"
                    key={deptId}
                    style={{
                      borderLeft:
                        info.approval_status === "approved"
                          ? "4px solid #14745d"
                          : info.approval_status === "rejected"
                          ? "4px solid #dc2626"
                          : info.approval_status === "request_changes"
                          ? "4px solid #d97706"
                          : "4px solid #6b7280",
                    }}
                  >
                    <h4>
                      {info.department_name ?? deptId}
                      <span
                        className="status-badge"
                        style={{
                          marginLeft: "0.5rem",
                          fontSize: "0.7rem",
                          background:
                            info.approval_status === "approved"
                              ? "#d1fae5"
                              : info.approval_status === "rejected"
                              ? "#fee2e2"
                              : info.approval_status === "request_changes"
                              ? "#fef3c7"
                              : "#f3f4f6",
                          color:
                            info.approval_status === "approved"
                              ? "#065f46"
                              : info.approval_status === "rejected"
                              ? "#991b1b"
                              : info.approval_status === "request_changes"
                              ? "#92400e"
                              : "#374151",
                          padding: "0.15rem 0.45rem",
                          borderRadius: "999px",
                        }}
                      >
                        {info.approval_status === "approved"
                          ? "✅ Aprobado"
                          : info.approval_status === "rejected"
                          ? "❌ Rechazado"
                          : info.approval_status === "request_changes"
                          ? "🔄 Cambios solicitados"
                          : "⏳ Pendiente"}
                      </span>
                    </h4>
                    {info.draft_content && (
                      <details>
                        <summary>Ver sección propuesta</summary>
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

                    {/* Human-in-the-loop sign-off is only available after the proposal enters Part 3. */}
                    {ticket?.status === "esperando_aprobacion" &&
                      info.approval_status !== "approved" && (
                        <DepartmentApprovalUI
                          ticketId={pollId}
                          departmentId={deptId}
                          departmentName={info.department_name ?? deptId}
                          onComplete={async () => {
                            await Promise.all([loadDrafts(pollId), pollTicket(pollId)]);
                          }}
                        />
                      )}
                  </article>
                ))}

              {/* Generate button if not yet started */}
              {ticket?.status === "needs_human_review" &&
                !drafts && (
                  <div className="hero-actions" style={{ marginTop: "1rem" }}>
                    <button
                      className="btn btn-dark"
                      onClick={handleGenerate}
                      disabled={generating}
                    >
                      {generating ? "Generando propuesta…" : "Generar propuesta"}
                    </button>
                  </div>
                )}

              {ticket?.status === "esperando_aprobacion" && !drafts && (
                <div className="hero-actions" style={{ marginTop: "1rem" }}>
                  <button
                    className="btn btn-dark"
                    onClick={handleStartApproval}
                    disabled={approveStarting}
                  >
                    {approveStarting
                      ? "Iniciando aprobación…"
                      : "Iniciar flujo de aprobación"}
                  </button>
                </div>
              )}

              {genError && (
                <div className="notice notice-error" role="alert">
                  {genError}
                </div>
              )}
              {approveError && (
                <div className="notice notice-error" role="alert">
                  {approveError}
                </div>
              )}
            </div>
          )}

          {/* Part 3: Final document */}
          {ticket?.status === "terminado" && (
            <div>
              <h3>Documento final</h3>
              {loadingDoc && <p className="status-pending">Cargando documento final…</p>}
              {docError && (
                <div className="notice notice-error" role="alert">
                  {docError}
                </div>
              )}
              {finalDoc && (
                <div className="dept-card" style={{ borderLeft: "4px solid #14745d" }}>
                  <p>
                    <strong>Documento:</strong> {finalDoc.document_type ?? "Propuesta final"}
                  </p>
                  <p>
                    <strong>Generado:</strong>{" "}
                    {finalDoc.generated_at
                      ? new Date(finalDoc.generated_at).toLocaleString("es-ES")
                      : "—"}
                  </p>
                  <details open>
                    <summary>Ver documento completo</summary>
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        background: "#f9fafb",
                        padding: "0.75rem",
                        borderRadius: "0.5rem",
                        fontSize: "0.85rem",
                        maxHeight: "600px",
                        overflow: "auto",
                        border: "1px solid #e5e7eb",
                      }}
                    >
                      {finalDoc.content}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Ticket search and navigation */}
      <section className="panel">
        <h2>Tickets</h2>
        <label htmlFor="ticket-search">Buscar por ID de ticket o ID de RFP</label>
        <input
          id="ticket-search"
          type="search"
          value={ticketSearch}
          onChange={(event) => {
            setTicketSearch(event.target.value);
            setTicketPage(1);
          }}
          placeholder="Ej.: 8d873c9b"
          style={{ width: "100%", maxWidth: 520, margin: "0.5rem 0 1rem" }}
        />
        <div
          className="ticket-department-filter"
          style={{ display: "grid", gap: "0.45rem", width: "100%", maxWidth: 520, margin: "0.5rem 0 1rem" }}
        >
          <label htmlFor="ticket-department">Departamento</label>
          <select
            id="ticket-department"
            value={ticketDepartment}
            onChange={(event) => {
              setTicketDepartment(event.target.value);
              setTicketPage(1);
            }}
            style={{ width: "100%" }}
          >
            <option value="">Todos los departamentos</option>
            <option value="seleccion">Selección</option>
            <option value="capacitacion">Capacitación</option>
            <option value="soporte">Soporte</option>
          </select>
        </div>
        <div role="tablist" aria-label="Filtrar tickets" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
          {ticketTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={ticketTab === tab.id}
              onClick={() => {
                setTicketTab(tab.id);
                setTicketPage(1);
              }}
              className={ticketTab === tab.id ? "btn btn-dark" : "btn btn-light"}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {loadingList && <p>Cargando…</p>}
        {recentTickets.length === 0 && !loadingList && (
          <p className="empty-state">No hay tickets cargados. Sube una RFP para comenzar.</p>
        )}
        {recentTickets.length > 0 && visibleTickets.length === 0 && (
          <p className="empty-state">No hay tickets que coincidan con la búsqueda y pestaña seleccionadas.</p>
        )}
        {visibleTickets.length > 0 && (
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
              {visibleTickets.map((t) => (
                <tr key={t.ticket_id}>
                  <td>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        setActiveTicket(t.ticket_id);
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
        <nav aria-label="Paginación de tickets" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginTop: "1rem" }}>
          <button
            type="button"
            className="btn btn-outline"
            disabled={ticketPage <= 1 || loadingList}
            onClick={() => setTicketPage((page) => Math.max(1, page - 1))}
          >
            ← Anterior
          </button>
          {Array.from({ length: ticketPageCount }, (_, index) => index + 1).map((page) => (
            <button
              key={page}
              type="button"
              className={ticketPage === page ? "btn btn-dark" : "btn btn-outline"}
              aria-current={ticketPage === page ? "page" : undefined}
              disabled={loadingList}
              onClick={() => setTicketPage(page)}
            >
              {page}
            </button>
          ))}
          <button
            type="button"
            className="btn btn-outline"
            disabled={ticketPage >= ticketPageCount || loadingList}
            onClick={() => setTicketPage((page) => Math.min(ticketPageCount, page + 1))}
          >
            Siguiente →
          </button>
          <span style={{ marginLeft: "0.5rem" }}>
            Página {ticketPage} de {ticketPageCount} · {ticketTotal} tickets
          </span>
        </nav>
      </section>
    </main>
  );
}

// ── Department Approval UI (Part 3) ──────────────────────────────────

function DepartmentApprovalUI({
  ticketId,
  departmentId,
  departmentName,
  onComplete,
}: {
  ticketId: string;
  departmentId: string;
  departmentName: string;
  onComplete: () => void | Promise<void>;
}) {
  const [action, setAction] = useState<string>("");
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!action || submitting) return;

    const token = getStoredAccessToken();
    if (!token) {
      setError("Inicia sesión para continuar.");
      return;
    }

    setSubmitting(true);
    setError("");

    try {
      const response = await fetch(
        `/api/rfp/${ticketId}/approve/${departmentId}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ action, feedback }),
        }
      );
      const payload = await response.json().catch(() => ({}));

      if (response.status === 401 || response.status === 403) {
        clearStoredAccessToken();
        window.dispatchEvent(new Event("nexova:unauthorized"));
        return;
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "Error al registrar acción."
        );
      }

      await onComplete();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Error al enviar acción."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "0.75rem" }}>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          marginBottom: "0.5rem",
        }}
      >
        <button
          type="button"
          className={`btn ${action === "approve" ? "btn-dark" : ""}`}
          style={{
            background: action === "approve" ? undefined : "#f3f4f6",
            color: action === "approve" ? undefined : "#374151",
          }}
          onClick={() => setAction("approve")}
          disabled={submitting}
        >
          ✅ Aprobar
        </button>
        <button
          type="button"
          className={`btn ${action === "reject" ? "btn-dark" : ""}`}
          style={{
            background: action === "reject" ? undefined : "#f3f4f6",
            color: action === "reject" ? undefined : "#374151",
          }}
          onClick={() => setAction("reject")}
          disabled={submitting}
        >
          ❌ Rechazar
        </button>
        <button
          type="button"
          className={`btn ${action === "request_changes" ? "btn-dark" : ""}`}
          style={{
            background: action === "request_changes" ? undefined : "#f3f4f6",
            color: action === "request_changes" ? undefined : "#374151",
          }}
          onClick={() => setAction("request_changes")}
          disabled={submitting}
        >
          🔄 Solicitar cambios
        </button>
      </div>

      {(action === "reject" || action === "request_changes") && (
        <textarea
          placeholder={
            action === "reject"
              ? "Razón del rechazo (obligatorio)…"
              : "Describe los cambios solicitados (obligatorio)…"
          }
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          required
          disabled={submitting}
          rows={3}
          style={{
            width: "100%",
            padding: "0.5rem",
            borderRadius: "0.375rem",
            border: "1px solid #d1d5db",
            fontFamily: "inherit",
            fontSize: "0.85rem",
            marginBottom: "0.5rem",
            resize: "vertical",
          }}
        />
      )}

      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <button
          className="btn btn-dark"
          type="submit"
          disabled={!action || submitting}
        >
          {submitting
            ? "Enviando…"
            : action === "approve"
            ? `Enviar aprobación de ${departmentName}`
            : action === "reject"
            ? "Enviar rechazo"
            : action === "request_changes"
            ? "Enviar solicitud de cambios"
            : "Selecciona una acción"}
        </button>
      </div>

      {error && (
        <div
          className="notice notice-error"
          role="alert"
          style={{ marginTop: "0.5rem" }}
        >
          {error}
        </div>
      )}
    </form>
  );
}