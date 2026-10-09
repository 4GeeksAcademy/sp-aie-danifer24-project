import { AccountSessionError, getCurrentAccount, updateMyProfile } from "@/lib/account";
import { ACCESS_TOKEN_STORAGE_KEY } from "@/lib/auth";
import { changePassword, forgotPassword, resetPassword } from "@/lib/passwords";

const jsonResponse = (payload: unknown, status = 200): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
}) as unknown as Response;

const invalidJsonResponse = (status = 200): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => { throw new SyntaxError("invalid json"); },
}) as unknown as Response;

describe("account and password clients", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "valid-jwt");
    global.fetch = jest.fn();
  });

  it("loads and updates the account with bearer and JSON headers", async () => {
    const fetchMock = jest.mocked(global.fetch);
    const account = { email: "person@example.test", role: "user", profile: { id: 1, user_id: 1, name: "Person", phone: null, address: null } };
    fetchMock.mockResolvedValueOnce(jsonResponse(account));
    await expect(getCurrentAccount()).resolves.toEqual(account);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/me");
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBe("Bearer valid-jwt");

    fetchMock.mockResolvedValueOnce(jsonResponse(account.profile));
    await expect(updateMyProfile({ name: "Person", phone: null, address: null })).resolves.toEqual(account.profile);
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ name: "Person", phone: null, address: null });
  });

  it("clears a revoked session and reports absent session", async () => {
    jest.mocked(global.fetch).mockResolvedValueOnce(jsonResponse({}, 401));
    await expect(getCurrentAccount()).rejects.toBeInstanceOf(AccountSessionError);
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();

    await expect(getCurrentAccount()).rejects.toBeInstanceOf(AccountSessionError);
  });

  it("maps permission, not-found, server, invalid JSON, network and abort cases", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 403));
    await expect(getCurrentAccount()).rejects.toThrow("No tienes permiso");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 404));
    await expect(getCurrentAccount()).rejects.toThrow("No se encontró tu perfil");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 503));
    await expect(getCurrentAccount()).rejects.toThrow("El servicio no está disponible");
    fetchMock.mockResolvedValueOnce(invalidJsonResponse());
    await expect(getCurrentAccount()).rejects.toThrow("respuesta no válida");
    fetchMock.mockRejectedValueOnce(new Error("connection"));
    await expect(getCurrentAccount()).rejects.toThrow("No se pudo conectar");

    const controller = new AbortController();
    controller.abort();
    const abortError = Object.assign(new Error("Aborted"), { name: "AbortError" });
    fetchMock.mockRejectedValueOnce(abortError);
    await expect(getCurrentAccount(controller.signal)).rejects.toBe(abortError);
  });

  it("sends public password actions to their endpoint with expected bodies", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValue(jsonResponse({ message: "ok" }));

    await expect(forgotPassword("person@example.test")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/forgot-password");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ email: "person@example.test" });

    await expect(resetPassword("reset-jwt", "replacement-password")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/auth/reset-password");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ token: "reset-jwt", new_password: "replacement-password" });
  });

  it("requires a session for password change and clears an expired one", async () => {
    const fetchMock = jest.mocked(global.fetch);
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    await expect(changePassword("old", "new-password")).rejects.toThrow("Inicia sesión");
    expect(fetchMock).not.toHaveBeenCalled();

    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "old-jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 401));
    await expect(changePassword("old", "new-password")).rejects.toThrow("Tu sesión ha caducado");
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBe("Bearer old-jwt");
  });

  it("maps password validation, expired reset, incorrect current password and transport errors", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 400));
    await expect(resetPassword("bad-token", "replacement-password")).rejects.toThrow("enlace de recuperación no es válido");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 400));
    await expect(changePassword("wrong", "replacement-password")).rejects.toThrow("contraseña actual no es correcta");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 422));
    await expect(resetPassword("reset-jwt", "short")).rejects.toThrow("al menos 8 caracteres");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 503));
    await expect(forgotPassword("person@example.test")).rejects.toThrow("servicio no está disponible");
    fetchMock.mockRejectedValueOnce(new Error("private transport detail"));
    await expect(forgotPassword("person@example.test")).rejects.toThrow("No se pudo conectar");
  });
});
