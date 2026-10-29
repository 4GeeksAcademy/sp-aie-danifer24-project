import Link from "next/link";
import PasswordForm from "../../password-form";

export default function ChangePasswordPage() {
  return <section className="login-page"><div className="login-panel"><div className="login-heading"><h1>Cambiar contraseña</h1></div><PasswordForm change /><p className="auth-switch"><Link href="/account/profile">Volver a mi perfil</Link></p></div></section>;
}