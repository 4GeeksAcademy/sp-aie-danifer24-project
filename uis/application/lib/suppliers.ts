import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

export const categories = {
  job_boards: "Portales de empleo",
  ats_software: "Software ATS",
  assessment_tools: "Evaluación de candidatos",
  training_platforms: "Formación",
  payroll_and_hr_software: "Nóminas y RR. HH.",
  video_interview: "Videoentrevistas",
  background_check: "Verificación de antecedentes",
  office_and_facilities: "Oficinas e instalaciones",
  it_and_software_licenses: "Licencias y tecnología",
} as const;

export type Category = keyof typeof categories;
export type Country = "Spain" | "USA";
export type SupplierStatus = "active" | "suspended";

export interface SupplierInput {
  name: string;
  country: Country;
  categories: Category[];
  monthly_rate: number;
  currency: "EUR" | "USD";
  status: SupplierStatus;
  contract_renewal_date?: string;
  contact_email?: string;
  notes?: string;
}

export interface Supplier extends SupplierInput {
  id: number;
  updated_at: string;
}

const fieldNames: Record<string, string> = {
  name: "Nombre",
  country: "País",
  categories: "Categorías",
  monthly_rate: "Tarifa mensual",
  currency: "Moneda",
  status: "Estado",
  contract_renewal_date: "Renovación",
  contact_email: "Email",
};

function apiError(payload: unknown): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return "No se pudo completar la operación. Inténtalo de nuevo.";
  }
  if (typeof payload.detail === "string") return payload.detail;
  if (!Array.isArray(payload.detail)) return "La API ha rechazado los datos.";
  return payload.detail.map((error: unknown) => {
    if (!error || typeof error !== "object" || !("loc" in error)) return "Revisa los datos.";
    const location = Array.isArray(error.loc) ? error.loc : [];
    const field = location.find((part: unknown) => typeof part === "string" && part in fieldNames);
    const label = typeof field === "string" ? fieldNames[field] : "Datos";
    const type = "type" in error ? error.type : "";
    const message = type === "greater_than" ? "debe ser mayor que cero" :
      type === "enum" ? "elige una opción válida" :
      type === "missing" ? "campo obligatorio" : "valor no válido";
    return `${label}: ${message}.`;
  }).join(" ");
}

export async function suppliersRequest<T>(path = "", options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const headers = new Headers(options?.headers);
    headers.set("Content-Type", "application/json");
    const token = getStoredAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    response = await fetch(`/api/suppliers${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("No se pudo conectar con el directorio. Inténtalo de nuevo.");
  }
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      clearStoredAccessToken();
      window.dispatchEvent(new Event("nexova:unauthorized"));
    }
    const payload: unknown = await response.json().catch(() => null);
    throw new Error(response.status >= 500 ? "El servicio no está disponible. Inténtalo de nuevo." : apiError(payload));
  }
  return response.json() as Promise<T>;
}

export function money(amount: number, currency: string): string {
  return new Intl.NumberFormat("es-ES", { style: "currency", currency }).format(amount);
}

export function renewalSoon(value?: string): boolean {
  if (!value) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = (new Date(`${value}T00:00:00`).getTime() - today.getTime()) / 86400000;
  return days >= 0 && days <= 60;
}