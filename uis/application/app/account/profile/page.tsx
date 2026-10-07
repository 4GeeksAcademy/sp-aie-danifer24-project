"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, LoaderCircle, RefreshCw, Save } from "lucide-react";
import { AccountSessionError, getCurrentAccount, updateMyProfile, type CurrentAccount, type Profile } from "@/lib/account";

function profileFields(profile: Profile) {
  return { name: profile.name ?? "", phone: profile.phone ?? "", address: profile.address ?? "" };
}

export default function AccountProfilePage() {
  const router = useRouter();
  const [account, setAccount] = useState<CurrentAccount | null>(null);
  const [fields, setFields] = useState({ name: "", phone: "", address: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getCurrentAccount(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setAccount(data);
        setFields(profileFields(data.profile));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof AccountSessionError) router.replace("/login");
        else setError(error instanceof Error ? error.message : "No se pudo cargar tu perfil.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [router, attempt]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !account) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const profile = await updateMyProfile({
        name: fields.name.trim() || null,
        phone: fields.phone.trim() || null,
        address: fields.address.trim() || null,
      });
      setAccount({ ...account, profile });
      setFields(profileFields(profile));
      setNotice("Perfil actualizado correctamente.");
    } catch (error) {
      if (error instanceof AccountSessionError) router.replace("/login");
      else setError(error instanceof Error ? error.message : "No se pudo guardar el perfil.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="account-profile">
      <section className="page-heading">
        <div><div className="eyebrow">MI CUENTA / NEXOVA</div><h1>Mi perfil</h1></div>
      </section>

      {loading && <p className="notice" role="status"><LoaderCircle size={18} className="spinning" />Cargando perfil...</p>}
      {error && <div className="error-banner" role="alert"><AlertCircle size={20} /><span>{error}</span>
        {!account && !loading && <button className="text-button" onClick={() => { setError(""); setLoading(true); setAttempt((current) => current + 1); }}><RefreshCw size={16} /> Reintentar</button>}
      </div>}

      {account && !loading && <form className="profile-form" onSubmit={submit} aria-busy={busy}>
        <fieldset className="form-fields" disabled={busy}>
          <label htmlFor="profile-email">Correo electrónico<input id="profile-email" type="email" value={account.email} readOnly autoComplete="email" /></label>
          <label htmlFor="profile-name">Nombre<input id="profile-name" name="name" autoComplete="name" value={fields.name} onChange={(event) => { setFields({ ...fields, name: event.target.value }); setNotice(""); }} /></label>
          <label htmlFor="profile-phone">Teléfono<input id="profile-phone" name="phone" type="tel" autoComplete="tel" value={fields.phone} onChange={(event) => { setFields({ ...fields, phone: event.target.value }); setNotice(""); }} /></label>
          <label htmlFor="profile-address">Dirección<input id="profile-address" name="address" autoComplete="street-address" value={fields.address} onChange={(event) => { setFields({ ...fields, address: event.target.value }); setNotice(""); }} /></label>
        </fieldset>
        <div className="notice" role="status" aria-live="polite">{notice && <><CheckCircle2 size={18} />{notice}</>}</div>
        <footer className="profile-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? <LoaderCircle size={18} className="spinning" /> : <Save size={18} />}{busy ? "Guardando..." : "Guardar cambios"}</button></footer>
      </form>}
    </div>
  );
}