export const ACCESS_TOKEN_STORAGE_KEY = "nexova_access_token";

export function getStoredAccessToken(): string | null {
  return typeof window === "undefined"
    ? null
    : window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
}

export function storeAccessToken(token: string): void {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAccessToken(): void {
  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
}

export async function loginRequest(email: string, password: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
      cache: "no-store",
    });
  } catch {
    throw new Error("No se pudo conectar con la API. Comprueba que esté en funcionamiento e inténtalo de nuevo.");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("El correo electrónico o la contraseña no son correctos.");
    }
    if (response.status >= 500) {
      throw new Error("El servicio de autenticación no está disponible. Inténtalo de nuevo.");
    }
    if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
      throw new Error(payload.detail);
    }
    throw new Error("Revisa el correo y la contraseña e inténtalo de nuevo.");
  }

  if (!payload || typeof payload !== "object" || !("access_token" in payload) || typeof payload.access_token !== "string") {
    throw new Error("La API devolvió una respuesta de autenticación no válida.");
  }

  return payload.access_token;
}
