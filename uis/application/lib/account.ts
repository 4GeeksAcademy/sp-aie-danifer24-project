import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

export interface Profile {
  id: number;
  user_id: number;
  name: string | null;
  phone: string | null;
  address: string | null;
}

export interface CurrentAccount {
  email: string;
  role: string;
  profile: Profile;
}

export type ProfileInput = Pick<Profile, "name" | "phone" | "address">;

export class AccountSessionError extends Error {
  constructor() {
    super("Tu sesión ha caducado. Inicia sesión de nuevo.");
    this.name = "AccountSessionError";
  }
}

async function accountRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getStoredAccessToken();
  if (!token) throw new AccountSessionError();

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new Error("No se pudo conectar con la API. Inténtalo de nuevo.");
  }

  if (response.status === 401) {
    clearStoredAccessToken();
    throw new AccountSessionError();
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    if (response.status >= 500) throw new Error("El servicio no está disponible. Inténtalo de nuevo.");
    if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
      throw new Error(payload.detail);
    }
    throw new Error("No se pudo actualizar el perfil. Revisa los datos e inténtalo de nuevo.");
  }
  return response.json() as Promise<T>;
}

export function getCurrentAccount(signal?: AbortSignal): Promise<CurrentAccount> {
  return accountRequest("/api/auth/me", { signal });
}

export function updateMyProfile(input: ProfileInput): Promise<Profile> {
  return accountRequest("/api/profiles/me", { method: "PUT", body: JSON.stringify(input) });
}