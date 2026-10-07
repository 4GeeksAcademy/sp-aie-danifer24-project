const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const loginSubmit = document.querySelector("#login-submit");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(loginForm);
  loginSubmit.disabled = true;
  loginError.hidden = true;

  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: String(form.get("email") ?? "").trim(),
        password: String(form.get("password") ?? ""),
      }),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(response.status === 401
        ? "El correo electrónico o la contraseña no son correctos."
        : "No se pudo iniciar sesión. Inténtalo de nuevo.");
    }
    if (!payload || typeof payload.access_token !== "string" || !payload.access_token) {
      throw new Error("El servicio devolvió una respuesta de sesión no válida.");
    }
    window.localStorage.setItem("nexova_access_token", payload.access_token);
    window.location.replace("/");
  } catch (error) {
    loginError.textContent = error instanceof Error ? error.message : "No se pudo iniciar sesión.";
    loginError.hidden = false;
    loginSubmit.disabled = false;
  }
});