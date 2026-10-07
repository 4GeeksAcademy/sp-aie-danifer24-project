export const TOKEN_STORAGE_KEY = "nexova_access_token";

export class InvalidSessionError extends Error {
  constructor() {
    super("Inicia sesión para continuar.");
    this.name = "InvalidSessionError";
  }
}

export function readSessionToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function clearSessionToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export async function validateSession(signal: AbortSignal): Promise<void> {
  const token = readSessionToken();
  if (!token) throw new InvalidSessionError();
  let response: Response;
  try {
    response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("No se pudo verificar la sesión. Comprueba la conexión con la API.");
  }
  if (response.status === 401 || response.status === 403) {
    if (readSessionToken() === token) clearSessionToken();
    throw new InvalidSessionError();
  }
  if (!response.ok) throw new Error("El servicio de autenticación no está disponible. Inténtalo de nuevo.");
  const payload: unknown = await response.json().catch(() => null);
  if (!payload || typeof payload !== "object" || !("email" in payload) || typeof payload.email !== "string") {
    throw new Error("La API devolvió una respuesta de sesión no válida.");
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
      cache: "no-store",
    });
  } catch {
    throw new Error("No se pudo conectar con la API. Inténtalo de nuevo.");
  }
  if (response.status === 401) throw new Error("El correo electrónico o la contraseña no son correctos.");
  if (!response.ok) throw new Error("No se pudo iniciar sesión. Revisa tus datos o inténtalo más tarde.");
  const payload: unknown = await response.json().catch(() => null);
  if (!payload || typeof payload !== "object" || !("access_token" in payload) || typeof payload.access_token !== "string" || !payload.access_token) {
    throw new Error("La API devolvió una respuesta de autenticación no válida.");
  }
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, payload.access_token);
  } catch {
    throw new Error("El navegador no permite guardar la sesión. Habilita el almacenamiento local.");
  }
}