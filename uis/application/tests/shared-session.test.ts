import {
  clearSessionToken,
  InvalidSessionError,
  readSessionToken,
  signIn,
  TOKEN_STORAGE_KEY,
  validateSession,
} from "@/../../packages/shared/auth/session";

const jsonResponse = (payload: unknown, status = 200): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
}) as Response;

describe("shared authentication session utilities", () => {
  beforeEach(() => {
    window.localStorage.clear();
    global.fetch = jest.fn();
  });

  describe("readSessionToken and clearSessionToken", () => {
    it("reads and clears the access token", () => {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");

      expect(readSessionToken()).toBe("access-token");
      clearSessionToken();
      expect(readSessionToken()).toBeNull();
    });

    it("fails closed when browser storage is unavailable", () => {
      const getItem = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
      expect(readSessionToken()).toBeNull();
      getItem.mockRestore();

      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");
      const removeItem = jest.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
      expect(() => clearSessionToken()).not.toThrow();
      removeItem.mockRestore();
    });
  });

  describe("validateSession", () => {
    it("validates the bearer token with the API", async () => {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");
      const fetchMock = jest.mocked(global.fetch);
      fetchMock.mockResolvedValueOnce(jsonResponse({ email: "person@example.test" }));
      const controller = new AbortController();

      await expect(validateSession(controller.signal)).resolves.toBeUndefined();
      expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({
        headers: { Authorization: "Bearer access-token" },
        cache: "no-store",
        signal: controller.signal,
      }));
    });

    it("rejects absent, revoked, invalid and unavailable sessions safely", async () => {
      const fetchMock = jest.mocked(global.fetch);
      const controller = new AbortController();
      await expect(validateSession(controller.signal)).rejects.toBeInstanceOf(InvalidSessionError);
      expect(fetchMock).not.toHaveBeenCalled();

      window.localStorage.setItem(TOKEN_STORAGE_KEY, "bad-token");
      fetchMock.mockResolvedValueOnce(jsonResponse({}, 401));
      await expect(validateSession(controller.signal)).rejects.toBeInstanceOf(InvalidSessionError);
      expect(readSessionToken()).toBeNull();

      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");
      fetchMock.mockImplementationOnce(async () => {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, "rotated-token");
        return jsonResponse({}, 401);
      });
      await expect(validateSession(controller.signal)).rejects.toBeInstanceOf(InvalidSessionError);
      expect(readSessionToken()).toBe("rotated-token");

      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");
      fetchMock.mockResolvedValueOnce(jsonResponse({ email: 42 }));
      await expect(validateSession(controller.signal)).rejects.toThrow("respuesta de sesión no válida");

      fetchMock.mockResolvedValueOnce(jsonResponse({}, 403));
      await expect(validateSession(controller.signal)).rejects.toBeInstanceOf(InvalidSessionError);
      expect(readSessionToken()).toBeNull();

      window.localStorage.setItem(TOKEN_STORAGE_KEY, "access-token");
      fetchMock.mockResolvedValueOnce(jsonResponse({}, 503));
      await expect(validateSession(controller.signal)).rejects.toThrow("servicio de autenticación no está disponible");

      fetchMock.mockRejectedValueOnce(new Error("network details"));
      await expect(validateSession(controller.signal)).rejects.toThrow("No se pudo verificar la sesión");

      controller.abort();
      const abortError = Object.assign(new Error("Aborted"), { name: "AbortError" });
      fetchMock.mockRejectedValueOnce(abortError);
      await expect(validateSession(controller.signal)).rejects.toBe(abortError);
    });
  });

  describe("signIn", () => {
    it("normalizes the email and stores the returned access token", async () => {
      const fetchMock = jest.mocked(global.fetch);
      fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "new-token", token_type: "bearer" }));

      await expect(signIn(" person@example.test ", "password")).resolves.toBeUndefined();
      expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
        email: "person@example.test",
        password: "password",
      });
      expect(readSessionToken()).toBe("new-token");
    });

    it("rejects invalid credentials, malformed responses and transport failures", async () => {
      const fetchMock = jest.mocked(global.fetch);
      fetchMock.mockResolvedValueOnce(jsonResponse({}, 401));
      await expect(signIn("person@example.test", "wrong")).rejects.toThrow("correo electrónico o la contraseña no son correctos");

      fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "" }));
      await expect(signIn("person@example.test", "password")).rejects.toThrow("respuesta de autenticación no válida");

      fetchMock.mockResolvedValueOnce(jsonResponse({}, 503));
      await expect(signIn("person@example.test", "password")).rejects.toThrow("No se pudo iniciar sesión");

      fetchMock.mockRejectedValueOnce(new Error("private network details"));
      await expect(signIn("person@example.test", "password")).rejects.toThrow("No se pudo conectar con la API");

      fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "valid-token" }));
      const setItem = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
      await expect(signIn("person@example.test", "password")).rejects.toThrow("El navegador no permite guardar la sesión");
      setItem.mockRestore();
    });
  });
});