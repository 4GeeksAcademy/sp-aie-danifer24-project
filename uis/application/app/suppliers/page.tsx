"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AlertCircle, ArrowUpRight, Building2, Check, CheckCircle2, Clock3, Pencil, Plus, RefreshCw, Search, X } from "lucide-react";
import { categories, isSupplier, isSupplierList, money, renewalSoon, suppliersRequest, type Category, type Country, type Supplier, type SupplierInput } from "@/lib/suppliers";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "No se pudo completar la operación.";
}

function formatDate(value?: string): string {
  if (!value) return "Fecha no disponible";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? "Fecha no disponible" : date.toLocaleDateString("es-ES");
}

function Modal({ title, onClose, busy, children }: { title: string; onClose: () => void; busy: boolean; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog ref={dialog} className="modal" aria-labelledby="modal-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <div className="modal-heading"><h2 id="modal-title">{title}</h2><button type="button" className="icon-button" title="Cerrar" aria-label="Cerrar" onClick={onClose} disabled={busy}><X size={20} /></button></div>
      {children}
    </dialog>
  );
}

function CreateSupplier({ onClose, onCreated }: { onClose: () => void; onCreated: (supplier: Supplier) => void }) {
  const [country, setCountry] = useState<Country>("Spain");
  const [selected, setSelected] = useState<Category[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const currency = country === "Spain" ? "EUR" : "USD";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected.length) { setError("Selecciona al menos una categoría."); return; }
    const form = new FormData(event.currentTarget);
    const payload: SupplierInput = {
      name: String(form.get("name")).trim(), country, categories: selected,
      monthly_rate: Number(form.get("monthly_rate")), currency,
      status: form.get("status") === "suspended" ? "suspended" : "active",
    };
    if (!payload.name) { setError("El nombre es obligatorio."); return; }
    if (!Number.isFinite(payload.monthly_rate) || payload.monthly_rate <= 0) { setError("La tarifa mensual debe ser mayor que cero."); return; }
    for (const field of ["contract_renewal_date", "contact_email", "notes"] as const) {
      const value = String(form.get(field) ?? "").trim();
      if (value) payload[field] = value;
    }
    setBusy(true); setError("");
    try {
      const supplier = await suppliersRequest<Supplier>("", { method: "POST", body: JSON.stringify(payload) });
      if (!isSupplier(supplier)) throw new Error("El directorio devolvió un proveedor no válido. Inténtalo de nuevo.");
      onCreated(supplier);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return (
    <Modal title="Nuevo proveedor" onClose={onClose} busy={busy}>
      <form onSubmit={submit}>
        <fieldset className="form-fields" disabled={busy}>
          <label>Nombre comercial <span className="required">*</span><input name="name" required maxLength={200} autoFocus autoComplete="organization" /></label>
          <div className="form-grid">
            <label>País <span className="required">*</span><select value={country} onChange={(event) => setCountry(event.target.value as Country)}><option value="Spain">España</option><option value="USA">Estados Unidos</option></select></label>
            <label>Tarifa mensual ({currency}) <span className="required">*</span><input type="number" name="monthly_rate" min="0.01" step="0.01" required inputMode="decimal" /></label>
          </div>
          <fieldset className="category-options"><legend>Categorías <span className="required">*</span></legend>
            {Object.entries(categories).map(([value, label]) => <label key={value}><input type="checkbox" checked={selected.includes(value as Category)} onChange={(event) => setSelected(event.target.checked ? [...selected, value as Category] : selected.filter((item) => item !== value))} />{label}</label>)}
          </fieldset>
          <div className="form-grid">
            <label>Estado<select name="status"><option value="active">Activo</option><option value="suspended">Suspendido</option></select></label>
            <label>Renovación del contrato<input type="date" name="contract_renewal_date" /></label>
          </div>
          <label>Email de contacto<input type="email" name="contact_email" autoComplete="email" /></label>
          <label>Notas<textarea name="notes" rows={3} /></label>
        </fieldset>
        {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}
        <footer className="modal-footer"><button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancelar</button><button className="primary-button" disabled={busy}><Plus size={17} />{busy ? "Guardando…" : "Registrar proveedor"}</button></footer>
      </form>
    </Modal>
  );
}

function EditRate({ supplier, onClose, onUpdated }: { supplier: Supplier; onClose: () => void; onUpdated: (supplier: Supplier) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rate = Number(new FormData(event.currentTarget).get("monthly_rate"));
    if (!Number.isFinite(rate) || rate <= 0) { setError("La tarifa mensual debe ser mayor que cero."); return; }
    setBusy(true); setError("");
    try {
      const updated = await suppliersRequest<Supplier>(`/${supplier.id}/rate`, { method: "PATCH", body: JSON.stringify({ monthly_rate: rate }) });
      if (!isSupplier(updated)) throw new Error("El directorio devolvió un proveedor no válido. Inténtalo de nuevo.");
      onUpdated(updated);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return (
    <Modal title="Actualizar tarifa" onClose={onClose} busy={busy}>
      <p className="modal-supplier-name">{supplier.name}</p>
      <form onSubmit={submit}>
        <label>Tarifa mensual ({supplier.currency})<input name="monthly_rate" type="number" min="0.01" step="0.01" required defaultValue={supplier.monthly_rate} autoFocus disabled={busy} inputMode="decimal" /></label>
        {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}
        <footer className="modal-footer"><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancelar</button><button className="primary-button" disabled={busy}><Check size={17} />{busy ? "Guardando…" : "Guardar tarifa"}</button></footer>
      </form>
    </Modal>
  );
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [country, setCountry] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    suppliersRequest<Supplier[]>("", { signal: controller.signal })
      .then((data) => {
        if (!isSupplierList(data)) throw new Error("El directorio devolvió una respuesta no válida. Inténtalo de nuevo.");
        setSuppliers(data);
        setError("");
      })
      .catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function reload() {
    setLoading(true); setError(""); setNotice("");
    try {
      const data = await suppliersRequest<Supplier[]>();
      if (!isSupplierList(data)) throw new Error("El directorio devolvió una respuesta no válida. Inténtalo de nuevo.");
      setSuppliers(data);
    }
    catch (error) { setError(errorMessage(error)); }
    finally { setLoading(false); }
  }

  async function toggleStatus(supplier: Supplier) {
    setPendingId(supplier.id); setError(""); setNotice("");
    try {
      const updated = await suppliersRequest<Supplier>(`/${supplier.id}/status`, { method: "PATCH", body: JSON.stringify({ status: supplier.status === "active" ? "suspended" : "active" }) });
      if (!isSupplier(updated)) throw new Error("El directorio devolvió un proveedor no válido. Inténtalo de nuevo.");
      setSuppliers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${supplier.name}: ${updated.status === "active" ? "activado" : "suspendido"}.`);
    } catch (error) { setError(errorMessage(error)); }
    finally { setPendingId(null); }
  }

  const filtered = suppliers.filter((supplier) => (!country || supplier.country === country) && (!category || (supplier.categories ?? []).includes(category as Category)) && (supplier.name ?? "").toLocaleLowerCase("es").includes(search.trim().toLocaleLowerCase("es")));
  const active = filtered.filter((supplier) => supplier.status === "active");
  const totals = ["EUR", "USD"].map((currency) => ({ currency, amount: active.filter((supplier) => supplier.currency === currency).reduce((total, supplier) => total + (supplier.monthly_rate ?? 0), 0) }));
  const hasFilters = Boolean(country || category || search);

  return (
    <div className="directory">
      <section className="page-heading">
        <div><div className="eyebrow">DIRECTORIO / NEXOVA</div><h1>Proveedores</h1><p className="page-subtitle">Servicios y contratos · España y Estados Unidos</p></div>
        <button className="primary-button" onClick={() => { setNotice(""); setCreating(true); }} disabled={loading || pendingId !== null}><Plus size={18} />Nuevo proveedor</button>
      </section>

      <section className="summary-band" aria-label="Resumen del directorio">
        <div><span>Proveedores</span><strong>{loading && !suppliers.length ? "—" : filtered.length}</strong></div>
        <div><span><span className="status-dot active" />Activos</span><strong>{active.length}</strong></div>
        <div><span><span className="status-dot suspended" />Suspendidos</span><strong>{filtered.length - active.length}</strong></div>
        <div className="cost-summary"><span>Coste mensual activo</span><div>{totals.map(({ currency, amount }) => <strong key={currency}>{money(amount, currency)}</strong>)}</div></div>
      </section>

      <section className="directory-controls" aria-label="Filtros de proveedores">
        <label className="search-field"><Search size={18} /><input aria-label="Buscar proveedor" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar proveedor" type="search" /></label>
        <label className="filter-field"><span>País</span><select aria-label="Filtrar por país" value={country} onChange={(event) => setCountry(event.target.value)}><option value="">Todos los países</option><option value="Spain">España</option><option value="USA">Estados Unidos</option></select></label>
        <label className="filter-field"><span>Categoría</span><select aria-label="Filtrar por categoría" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Todas las categorías</option>{Object.entries(categories).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        {hasFilters && <button className="icon-button" onClick={() => { setCountry(""); setCategory(""); setSearch(""); }} aria-label="Limpiar filtros" title="Limpiar filtros"><X size={18} /></button>}
        <button className="icon-button refresh-button" onClick={reload} aria-label="Actualizar listado" title="Actualizar listado" disabled={loading || pendingId !== null}><RefreshCw size={18} className={loading ? "spinning" : ""} /></button>
      </section>

      {error && <div className="error-banner" role="alert"><AlertCircle size={20} /><span>{error}</span><button onClick={reload} className="text-button" disabled={loading}>Reintentar</button></div>}
      <div className="notice" role="status" aria-live="polite">{notice && <><CheckCircle2 size={17} />{notice}</>}</div>

      <section className="table-section" aria-label="Listado de proveedores" aria-busy={loading}>
        <div className="table-scroll">
          <table>
            <thead><tr><th scope="col">Proveedor</th><th scope="col">País</th><th scope="col">Categorías</th><th scope="col">Tarifa mensual</th><th scope="col">Renovación</th><th scope="col">Estado</th></tr></thead>
            <tbody>
              {filtered.map((supplier) => (
                <tr key={supplier.id} className={supplier.status === "suspended" ? "suspended-row" : ""}>
                  <td className="supplier-cell"><div className="supplier-content"><div className="supplier-avatar" aria-hidden="true">{supplier.name?.charAt(0) || "?"}</div><div><strong>{supplier.name ?? "Proveedor"}</strong>{supplier.contact_email && <a className="contact-link" href={`mailto:${supplier.contact_email}`}>{supplier.contact_email}<ArrowUpRight size={11} /></a>}</div></div></td>
                  <td data-label="País"><span className="country-code">{supplier.country === "Spain" ? "ES" : supplier.country === "USA" ? "US" : "—"}</span>{supplier.country === "Spain" ? "España" : supplier.country === "USA" ? "Estados Unidos" : "País no disponible"}</td>
                  <td data-label="Categorías" className="categories-cell"><div className="category-tags">{(supplier.categories ?? []).map((value) => <span key={value}>{categories[value] ?? "Otra categoría"}</span>)}</div></td>
                  <td data-label="Tarifa mensual"><div className="rate-cell"><span className="rate-number">{money(supplier.monthly_rate ?? 0, supplier.currency ?? "EUR")}</span><button className="icon-button edit-button" onClick={() => setEditing(supplier)} disabled={pendingId !== null || loading} title={`Editar tarifa de ${supplier.name ?? "proveedor"}`} aria-label={`Editar tarifa de ${supplier.name ?? "proveedor"}`}><Pencil size={15} /></button></div><span className="updated-date">Actualizada {formatDate(supplier.updated_at)}</span></td>
                  <td data-label="Renovación"><span className={renewalSoon(supplier.contract_renewal_date) ? "renewal-soon" : "renewal-date"}>{renewalSoon(supplier.contract_renewal_date) && <Clock3 size={14} />}{supplier.contract_renewal_date ? formatDate(supplier.contract_renewal_date) : "Sin fecha"}</span></td>
                  <td data-label="Estado"><div className="status-cell"><span className={`status-badge ${supplier.status ?? "unknown"}`}><span className={`status-dot ${supplier.status ?? "unknown"}`} />{supplier.status === "active" ? "Activo" : supplier.status === "suspended" ? "Suspendido" : "No disponible"}</span><label className="status-toggle" title={`${supplier.status === "active" ? "Suspender" : "Activar"} ${supplier.name ?? "proveedor"}`}><input type="checkbox" role="switch" checked={supplier.status === "active"} aria-label={`${supplier.status === "active" ? "Suspender" : "Activar"} ${supplier.name ?? "proveedor"}`} disabled={pendingId !== null || loading} onChange={() => toggleStatus(supplier)} /><span aria-hidden="true" /></label></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length && <div className="empty-state"><Building2 size={30} /><h2>{loading ? "Cargando proveedores…" : error ? "No se pudo cargar el directorio" : hasFilters ? "Sin coincidencias" : "No hay proveedores"}</h2>{!loading && !error && (hasFilters ? <button className="secondary-button" onClick={() => { setCountry(""); setCategory(""); setSearch(""); }}>Limpiar filtros</button> : <button className="primary-button" onClick={() => setCreating(true)}><Plus size={17} />Nuevo proveedor</button>)}</div>}
        <footer className="table-footer"><span>{filtered.length} de {suppliers.length} proveedores</span><span>Tarifas en la moneda del contrato</span></footer>
      </section>

      {creating && <CreateSupplier onClose={() => setCreating(false)} onCreated={(supplier) => { setSuppliers((current) => [...current, supplier]); setCountry(""); setCategory(""); setSearch(""); setCreating(false); setNotice(`${supplier.name} registrado.`); }} />}
      {editing && <EditRate supplier={editing} onClose={() => setEditing(null)} onUpdated={(supplier) => { setSuppliers((current) => current.map((item) => item.id === supplier.id ? supplier : item)); setEditing(null); setNotice(`Tarifa de ${supplier.name} actualizada.`); }} />}
    </div>
  );
}