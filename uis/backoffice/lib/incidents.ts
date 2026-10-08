export const INCIDENT_STATUSES = ["open", "in_progress", "resolved", "discarded"] as const;
export const INCIDENT_ORIGINS = ["customer", "branch", "internal"] as const;
export const INCIDENT_BRANCHES = ["central", "valencia_operations", "miami_office", "remote"] as const;
export const INCIDENT_CATEGORIES = [
  "technical_failure",
  "process_error",
  "client_complaint",
  "candidate_issue",
  "staff_issue",
  "sla_breach",
  "data_quality",
  "other",
] as const;

export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];
export type IncidentOrigin = (typeof INCIDENT_ORIGINS)[number];
export type IncidentBranch = (typeof INCIDENT_BRANCHES)[number];
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number];

export type Incident = {
  id: number;
  title: string;
  description: string;
  category: IncidentCategory;
  status: IncidentStatus;
  origin: IncidentOrigin;
  branch: IncidentBranch;
  created_at: string;
  updated_at: string;
};

export type IncidentSummary = {
  total: number;
  by_status: Record<IncidentStatus, number>;
  by_category: Record<IncidentCategory, number>;
  by_origin: Record<IncidentOrigin, number>;
  by_branch: Record<IncidentBranch, number>;
};

export const STATUS_LABELS: Record<IncidentStatus, string> = {
  open: "Abierta",
  in_progress: "En curso",
  resolved: "Resuelta",
  discarded: "Descartada",
};

export const ORIGIN_LABELS: Record<IncidentOrigin, string> = {
  customer: "Cliente",
  branch: "Sede",
  internal: "Interno",
};

export const BRANCH_LABELS: Record<IncidentBranch, string> = {
  central: "Central — Sede Valencia",
  valencia_operations: "Valencia — Operaciones",
  miami_office: "Miami Office",
  remote: "Remoto (empleado sin sede fija)",
};

export const CATEGORY_LABELS: Record<IncidentCategory, string> = {
  technical_failure: "Fallo técnico",
  process_error: "Error de proceso",
  client_complaint: "Queja de cliente",
  candidate_issue: "Problema de candidato",
  staff_issue: "Incidencia de personal",
  sla_breach: "Incumplimiento de SLA",
  data_quality: "Calidad de datos",
  other: "Otro",
};

export const NEXT_STATUSES: Record<IncidentStatus, IncidentStatus[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded"],
  resolved: [],
  discarded: [],
};

const API_ROOT = "/api/incidents";

function readSessionToken(): string | null {
  try {
    return window.localStorage.getItem("nexova_access_token");
  } catch {
    return null;
  }
}

function fieldMessage(field: unknown): string {
  const messages: Record<string, string> = {
    title: "El título es obligatorio.",
    description: "La descripción es obligatoria.",
    category: "Selecciona una categoría válida.",
    status: "No se pudo aplicar ese cambio de estado. Actualiza la incidencia e inténtalo de nuevo.",
    origin: "Selecciona un origen válido.",
    branch: "Selecciona una sede válida.",
  };
  return typeof field === "string" ? messages[field] ?? "Revisa los datos e inténtalo de nuevo." : "Revisa los datos e inténtalo de nuevo.";
}

export class IncidentApiError extends Error {
  field?: string;

  constructor(message: string, field?: string) {
    super(message);
    this.name = "IncidentApiError";
    this.field = field;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = typeof window === "undefined" ? null : readSessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(path, { ...options, headers, cache: "no-store" });
  } catch {
    throw new IncidentApiError("No se pudo conectar con el servicio. Comprueba tu conexión e inténtalo de nuevo.");
  }

  if (response.status === 401 || response.status === 403) {
    if (typeof window !== "undefined") window.dispatchEvent(new Event("nexova:unauthorized"));
    throw new IncidentApiError("Tu sesión ha caducado. Inicia sesión de nuevo.");
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const outerDetail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    const errors = payload && typeof payload === "object" && "errors" in payload
      ? payload.errors
      : outerDetail && typeof outerDetail === "object" && "errors" in outerDetail
        ? outerDetail.errors
        : null;
    if (Array.isArray(errors) && errors.length) {
      const first = errors[0] as { field?: unknown; message?: unknown };
      const field = typeof first.field === "string" ? first.field : undefined;
      throw new IncidentApiError(fieldMessage(field), field);
    }
    const detail = outerDetail;
    if (detail && typeof detail === "object" && "field" in detail) {
      const field = typeof detail.field === "string" ? detail.field : undefined;
      throw new IncidentApiError(fieldMessage(field), field);
    }
    const fallback = response.status >= 500
      ? "El servicio no está disponible ahora. Inténtalo de nuevo más tarde."
      : "No se pudo guardar la incidencia. Revisa los datos e inténtalo de nuevo.";
    throw new IncidentApiError(fallback);
  }
  try {
    return await response.json() as T;
  } catch {
    throw new IncidentApiError("El servicio de incidencias devolvió una respuesta no válida. Inténtalo de nuevo.");
  }
}

export function createIncident(input: Omit<Incident, "id" | "created_at" | "updated_at">): Promise<Incident> {
  return request<Incident>(API_ROOT, { method: "POST", body: JSON.stringify(input) });
}

export function listIncidents(filters: Partial<Pick<Incident, "status" | "origin" | "branch">> = {}): Promise<Incident[]> {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  return request<Incident[]>(`${API_ROOT}${query.size ? `?${query}` : ""}`);
}

export function updateIncidentStatus(id: number, status: IncidentStatus): Promise<Incident> {
  return request<Incident>(`${API_ROOT}/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function getIncidentSummary(): Promise<IncidentSummary> {
  return request<IncidentSummary>(`${API_ROOT}/summary`);
}

export function readableError(error: unknown): string {
  if (error instanceof IncidentApiError) return error.message;
  return "Ha ocurrido un problema inesperado. Inténtalo de nuevo.";
}