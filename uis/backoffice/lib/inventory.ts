export type InventoryOffice = "Valencia" | "Miami";
export type AssetCategory = "hardware" | "peripherals" | "office_supplies" | "training_materials";

export type Asset = {
  id: number;
  name: string;
  sku: string;
  category: AssetCategory;
  office: InventoryOffice;
  current_stock: number;
};

export type AssetInput = Omit<Asset, "id" | "current_stock">;

export type AssetEntryInput = {
  asset_id: number;
  quantity: number;
  supplier: string;
  office: InventoryOffice;
};

export type AssetEntry = AssetEntryInput & {
  id: number;
  created_at: string;
  user_uuid: string;
};

export type AssetExitInput = {
  asset_id: number;
  quantity: number;
  exit_type: "allocation" | "consumption";
  assigned_to: string | null;
  office: InventoryOffice;
};

export type AssetExit = AssetExitInput & {
  id: number;
  created_at: string;
  user_uuid: string;
};

export type InventoryOrder =
  | (AssetEntry & { order_type: "inbound"; asset: Asset })
  | (AssetExit & { order_type: "outbound"; asset: Asset });

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

export function getAsset(id: number): Promise<Asset> {
  return request<Asset>(`products/${encodeURIComponent(id)}`);
}

export function createAsset(input: AssetInput): Promise<Asset> {
  return request<Asset>("products", { method: "POST", body: JSON.stringify(input) }, true);
}

export function createAssetEntry(input: AssetEntryInput): Promise<AssetEntry> {
  return request<AssetEntry>("orders/inbound", { method: "POST", body: JSON.stringify(input) }, true);
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
