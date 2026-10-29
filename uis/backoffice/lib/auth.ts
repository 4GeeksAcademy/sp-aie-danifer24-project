export const ACCESS_TOKEN_STORAGE_KEY = "nexova_access_token";

export type RegistrationField = "email" | "password" | "name" | "phone" | "address";
export type RegistrationFieldErrors = Partial<Record<RegistrationField, string>>;
const registrationFields: RegistrationField[] = ["email", "password", "name", "phone", "address"];

export interface RegistrationInput {
  email: string;
  password: string;
  name?: string;
  phone?: string;
  address?: string;
}

export class RegistrationError extends Error {
  constructor(readonly fieldErrors: RegistrationFieldErrors) {
    super("Revisa los campos marcados.");
    this.name = "RegistrationError";
  }
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    throw new Error("El navegador no permite acceder a la sesión. Habilita el almacenamiento local e inténtalo de nuevo.");
  }
}

export function storeAccessToken(token: string): void {
  try {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  } catch {
    throw new Error("El navegador no permite guardar la sesión. Habilita el almacenamiento local e inténtalo de nuevo.");
  }
}

export function clearStoredAccessToken(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    window.dispatchEvent(new Event("nexova:unauthorized"));
  }
}

function parseRegistrationErrors(payload: unknown): RegistrationFieldErrors {
  if (!payload || typeof payload !== "object" || !("detail" in payload) || !Array.isArray(payload.detail)) {
    return {};
  }

  const fieldErrors: RegistrationFieldErrors = {};
  for (const issue of payload.detail) {
    if (!issue || typeof issue !== "object" || !("loc" in issue) || !Array.isArray(issue.loc)) continue;
    const location = issue.loc as unknown[];
    const field = location.find((part: unknown): part is RegistrationField =>
      typeof part === "string" && registrationFields.includes(part as RegistrationField),
    );
    if (!field || fieldErrors[field]) continue;

    const type = "type" in issue && typeof issue.type === "string" ? issue.type : "";
    if (type === "missing") {
      fieldErrors[field] = "Este campo es obligatorio.";
    } else if (field === "email") {
      fieldErrors[field] = "Introduce una dirección de correo válida.";
    } else if (field === "password" && type === "string_too_short") {
      fieldErrors[field] = "La contraseña debe tener al menos 8 caracteres.";
    } else if (field === "password") {
      fieldErrors[field] = "La contraseña no puede superar 72 bytes.";
    } else {
      fieldErrors[field] = "Revisa este campo.";
    }
  }

  return fieldErrors;
}

export async function registerRequest(input: RegistrationInput): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      cache: "no-store",
    });
  } catch {
    throw new Error("No se pudo conectar con la API. Comprueba que esté en funcionamiento e inténtalo de nuevo.");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (response.ok) return;

  if (response.status === 409) {
    throw new RegistrationError({ email: "Este correo ya está registrado." });
  }
  if (response.status === 422) {
    const fieldErrors = parseRegistrationErrors(payload);
    if (Object.keys(fieldErrors).length) throw new RegistrationError(fieldErrors);
  }
  if (response.status >= 500) {
    throw new Error("El servicio de registro no está disponible. Inténtalo de nuevo.");
  }
  throw new Error("No se pudo crear la cuenta. Revisa los datos e inténtalo de nuevo.");
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
    throw new Error("Revisa el correo y la contraseña e inténtalo de nuevo.");
  }

  if (!payload || typeof payload !== "object" || !("access_token" in payload) || typeof payload.access_token !== "string") {
    throw new Error("La API devolvió una respuesta de autenticación no válida.");
  }

  return payload.access_token;
}