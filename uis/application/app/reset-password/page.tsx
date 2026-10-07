import PasswordForm from "../password-form";

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : undefined;
  return <section className="login-page"><div className="login-panel"><div className="login-heading"><h1>Restablecer contraseña</h1></div><PasswordForm token={token} /></div></section>;
}