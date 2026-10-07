import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

async function passwordRequest(endpoint: string, body: Record<string, string>, authenticated = false): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (authenticated) {
    const token = getStoredAccessToken();
    if (!token) {
      window.dispatchEvent(new Event("nexova:unauthorized"));
      throw new Error("Inicia sesión para cambiar tu contraseña.");
    }
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`/api/auth/${endpoint}`, { method: "POST", headers, body: JSON.stringify(body), cache: "no-store" });
  } catch {
    throw new Error("No se pudo conectar con la API. Inténtalo de nuevo.");
  }
  if (response.ok) return;
  if (authenticated && response.status === 401) {
    clearStoredAccessToken();
    window.dispatchEvent(new Event("nexova:unauthorized"));
    throw new Error("Tu sesión ha caducado. Inicia sesión de nuevo.");
  }
  const payload: unknown = await response.json().catch(() => null);
  if (response.status >= 500) throw new Error("El servicio no está disponible. Inténtalo de nuevo.");
  if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
    throw new Error(payload.detail);
  }
  if (response.status === 422) throw new Error("Revisa los datos. La nueva contraseña debe tener al menos 8 caracteres y no superar 72 bytes.");
  throw new Error("No se pudo completar la solicitud. Inténtalo de nuevo.");
}

export function forgotPassword(email: string): Promise<void> {
  return passwordRequest("forgot-password", { email });
}

export function resetPassword(token: string, newPassword: string): Promise<void> {
  return passwordRequest("reset-password", { token, new_password: newPassword });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return passwordRequest("change-password", { current_password: currentPassword, new_password: newPassword }, true);
}