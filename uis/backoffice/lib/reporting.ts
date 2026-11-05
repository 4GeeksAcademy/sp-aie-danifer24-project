import { track } from "@/lib/telemetry";

export type WeeklyKpiEntry = {
  office: "valencia" | "miami";
  programme_id: string;
  total_material_cost: number;
  kits_delivered_count: number;
  shortage_events_count: number;
  cost_variance_events_count: number;
  currency: "EUR" | "USD";
};

export type WeeklyKpiReport = {
  week_start: string;
  entries: WeeklyKpiEntry[];
};

function isEntry(value: unknown): value is WeeklyKpiEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<WeeklyKpiEntry>;
  return (entry.office === "valencia" || entry.office === "miami")
    && typeof entry.programme_id === "string"
    && typeof entry.total_material_cost === "number" && Number.isFinite(entry.total_material_cost)
    && typeof entry.kits_delivered_count === "number" && Number.isInteger(entry.kits_delivered_count)
    && typeof entry.shortage_events_count === "number" && Number.isInteger(entry.shortage_events_count)
    && typeof entry.cost_variance_events_count === "number" && Number.isInteger(entry.cost_variance_events_count)
    && (entry.currency === "EUR" || entry.currency === "USD");
}

export function isWeeklyKpiReport(value: unknown): value is WeeklyKpiReport {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<WeeklyKpiReport>;
  return typeof report.week_start === "string"
    && /^\d{4}-\d{2}-\d{2}$/.test(report.week_start)
    && Array.isArray(report.entries)
    && report.entries.every(isEntry);
}

export async function getWeeklyKpiReport(signal?: AbortSignal): Promise<WeeklyKpiReport> {
  const startedAt = performance.now();
  let response: Response;
  try {
    const token = window.localStorage.getItem("nexova_access_token");
    const headers = new Headers({ Accept: "application/json" });
    if (token) headers.set("Authorization", `Bearer ${token}`);
    response = await fetch("/api/reporting/weekly-office-program-performance", {
      headers,
      cache: "no-store",
      signal,
    });
  } catch {
    throw new Error("No se pudo conectar con el reporte. Comprueba tu conexión e inténtalo de nuevo.");
  }

  track("api_request_completed", {
    route_template: "/api/reporting/weekly-office-program-performance",
    method: "GET",
    status_code: response.status,
    duration_ms: Math.round(performance.now() - startedAt),
  });

  if (response.status === 401 || response.status === 403) {
    window.dispatchEvent(new Event("nexova:unauthorized"));
    throw new Error("Tu sesión ha caducado. Inicia sesión de nuevo.");
  }
  if (!response.ok) {
    if (response.status === 404) throw new Error("Todavía no hay un reporte semanal publicado.");
    throw new Error("No se pudo cargar el reporte semanal. Inténtalo de nuevo más tarde.");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!isWeeklyKpiReport(payload)) throw new Error("El reporte recibido no tiene un formato válido.");
  return payload;
}
