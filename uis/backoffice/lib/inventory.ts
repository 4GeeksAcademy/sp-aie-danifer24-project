import { track } from "@/lib/telemetry";
import { suppliersRequest, type Supplier } from "@/lib/suppliers";

export type InventoryOffice = "Valencia" | "Miami";
export type AssetCategory = "hardware" | "peripherals" | "office_supplies" | "training_materials";

export type Asset = {
  id: number;
  name: string;
  sku: string;
  category: AssetCategory;
  office: InventoryOffice;
  current_stock: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment" | null;
  programme_id: string | null;
};

export type AssetInput = Omit<Asset, "id" | "current_stock">;

export type AssetEntryInput = {
  asset_id: number;
  quantity: number;
  supplier_id: number;
  unit_cost: number;
  office: InventoryOffice;
};

export type AssetEntry = {
  id: number;
  quantity: number;
  supplier: string;
  supplier_id: number | null;
  unit_cost: number | null;
  office: InventoryOffice;
  created_at: string;
};

export type InventoryBusinessCategory = "training_kit" | "certification" | "onboarding_equipment";
export type InventoryProgramme = { id: string; name: string };

export const INVENTORY_PROGRAMMES: InventoryProgramme[] = [
  { id: "ventas-b2b", name: "Formación en ventas B2B" },
  { id: "liderazgo-basico", name: "Liderazgo básico" },
  { id: "onboarding-soporte", name: "Onboarding de soporte" },
];

export type AssetExitInput = {
  asset_id: number;
  quantity: number;
  exit_type: "allocation" | "consumption";
  assigned_to: string | null;
  office: InventoryOffice;
};

export type AssetExit = {
  id: number;
  quantity: number;
  exit_type: "allocation" | "consumption";
  assigned_to: string | null;
  office: InventoryOffice;
  created_at: string;
};

export type InventoryOrder =
  | { id: number; quantity: number; created_at: string; order_type: "inbound"; supplier: string; asset_name: string; asset_sku: string }
  | { id: number; quantity: number; created_at: string; order_type: "outbound"; exit_type: "allocation" | "consumption"; assigned_to: string | null; asset_name: string; asset_sku: string };

export class InventoryApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "InventoryApiError";
  }
}

function readSessionToken(): string | null {
  try {
    return window.localStorage.getItem("nexova_access_token");
  } catch {
    return null;
  }
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (!payload || typeof payload !== "object") return fallback;

  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const message = (item as Record<string, unknown>).msg ?? (item as Record<string, unknown>).message;
      return typeof message === "string" && message.trim() ? [message] : [];
    });
    if (messages.length) return messages.join(" ");
  }

  const message = record.message;
  if (typeof message === "string" && message.trim()) return message;
  return fallback;
}

async function request<T>(path: string, options: RequestInit = {}, protectedRoute = false): Promise<T> {
  const startedAt = performance.now();
  const pathname = path.split("?")[0];
  const routeTemplate = pathname === "products" ? "/inventory/products" :
    /^products\/\d+$/.test(pathname) ? "/inventory/products/{id}" :
    /^products\/\d+\/telemetry-metadata$/.test(pathname) ? "/inventory/products/{id}/telemetry-metadata" :
    pathname === "programmes" ? "/inventory/programmes" :
    pathname === "orders/inbound" ? "/inventory/orders/inbound" :
    pathname === "orders/outbound" ? "/inventory/orders/outbound" :
    pathname === "orders" ? "/inventory/orders" : "unmatched";
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");

  const token = typeof window === "undefined" ? null : readSessionToken();
  if (protectedRoute && !token) {
    throw new InventoryApiError("Inicia sesión para continuar.", 401);
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`/api/inventory/${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new InventoryApiError("No se pudo conectar con el servicio de inventario. Comprueba tu conexión e inténtalo de nuevo.");
  }
  track("api_request_completed", {
    route_template: routeTemplate,
    method,
    status_code: response.status,
    duration_ms: Math.round(performance.now() - startedAt),
  });

  if (response.status === 401 || response.status === 403) {
    if (typeof window !== "undefined") window.dispatchEvent(new Event("nexova:unauthorized"));
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const fallback = response.status >= 500
      ? "El servicio de inventario no está disponible ahora. Inténtalo de nuevo más tarde."
      : `No se pudo completar la solicitud de inventario (HTTP ${response.status}).`;
    throw new InventoryApiError(getErrorMessage(payload, fallback), response.status);
  }

  try {
    return await response.json() as T;
  } catch {
    throw new InventoryApiError("El servicio de inventario devolvió una respuesta no válida.", response.status);
  }
}

export function listAssets(): Promise<Asset[]> {
  return request<Asset[]>("products");
}

export function listInventoryProgrammes(): Promise<InventoryProgramme[]> {
  return request<InventoryProgramme[]>("programmes");
}

export function getAsset(id: number): Promise<Asset> {
  return request<Asset>(`products/${encodeURIComponent(id)}`);
}

export function createAsset(input: AssetInput): Promise<Asset> {
  return request<Asset>("products", { method: "POST", body: JSON.stringify(input) }, true);
}

export function createAssetEntry(input: AssetEntryInput): Promise<AssetEntry> {
  return request<AssetEntry>("orders/inbound", { method: "POST", body: JSON.stringify(input) }, true);
}

export function updateAssetTelemetryMetadata(
  id: number,
  metadata: { product_category: InventoryBusinessCategory; programme_id: string },
): Promise<Asset> {
  return request<Asset>(`products/${encodeURIComponent(id)}/telemetry-metadata`, {
    method: "PATCH",
    body: JSON.stringify(metadata),
  }, true);
}

export function listInventorySuppliers(): Promise<Supplier[]> {
  return suppliersRequest<Supplier[]>("");
}

export function createAssetExit(input: AssetExitInput): Promise<AssetExit> {
  return request<AssetExit>("orders/outbound", { method: "POST", body: JSON.stringify(input) }, true);
}

export function listInventoryOrders(): Promise<InventoryOrder[]> {
  return request<InventoryOrder[]>("orders", {}, true);
}

export function readableInventoryError(error: unknown): string {
  if (error instanceof InventoryApiError) return error.message;
  return "Ha ocurrido un problema inesperado al consultar el inventario.";
}
