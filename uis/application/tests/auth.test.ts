import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearStoredAccessToken,
  getStoredAccessToken,
  loginRequest,
  registerRequest,
  RegistrationError,
  storeAccessToken,
} from "@/lib/auth";

const jsonResponse = (payload: unknown, status = 200): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
}) as Response;

describe("auth client", () => {
  beforeEach(() => {
    window.localStorage.clear();
    global.fetch = jest.fn();
  });

  it("stores, reads and removes the expected session token", () => {
    storeAccessToken("jwt-value");
    expect(getStoredAccessToken()).toBe("jwt-value");
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("jwt-value");
    clearStoredAccessToken();
    expect(getStoredAccessToken()).toBeNull();
  });

  it("sends a normalized email and returns the access token", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValue(jsonResponse({ access_token: "jwt-value", token_type: "bearer" }));

    await expect(loginRequest("  PERSON@example.test ", "secret")).resolves.toBe("jwt-value");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "PERSON@example.test", password: "secret" });
    expect(init?.cache).toBe("no-store");
  });

  it("maps unauthorized, server, network and malformed success responses safely", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "sensitive backend info" }, 401));
    await expect(loginRequest("person@example.test", "wrong")).rejects.toThrow("El correo electrónico o la contraseña no son correctos.");

    fetchMock.mockResolvedValueOnce(jsonResponse({}, 503));
    await expect(loginRequest("person@example.test", "secret")).rejects.toThrow("El servicio de autenticación no está disponible.");

    fetchMock.mockRejectedValueOnce(new Error("private network details"));
    await expect(loginRequest("person@example.test", "secret")).rejects.toThrow("No se pudo conectar con la API.");

    fetchMock.mockResolvedValueOnce(jsonResponse({ token: "not-access-token" }));
    await expect(loginRequest("person@example.test", "secret")).rejects.toThrow("respuesta de autenticación no válida");
  });

  it("maps registration success, duplicate and validation fields", async () => {
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1 }, 201));
    await expect(registerRequest({ email: "person@example.test", password: "long-password" })).resolves.toBeUndefined();

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "duplicate" }, 409));
    await expect(registerRequest({ email: "person@example.test", password: "long-password" })).rejects.toMatchObject({
      name: "RegistrationError",
      fieldErrors: { email: "Este correo ya está registrado." },
    });

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [{ loc: ["body", "password"], type: "string_too_short" }] }, 422));
    await expect(registerRequest({ email: "person@example.test", password: "short" })).rejects.toMatchObject({
      name: "RegistrationError",
      fieldErrors: { password: "La contraseña debe tener al menos 8 caracteres." },
    } satisfies Partial<RegistrationError>);
  });

  it("reports blocked localStorage with a controlled message", () => {
    const getItem = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => getStoredAccessToken()).toThrow("El navegador no permite acceder a la sesión.");
    getItem.mockRestore();
  });
});
