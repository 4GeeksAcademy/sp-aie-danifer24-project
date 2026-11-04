"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { AlertCircle, ArrowUpRight, Building2, CheckCircle2, Clock3, Pencil, Plus, RefreshCw, Search, X } from "lucide-react";
import { categories, isSupplier, isSupplierList, money, renewalSoon, supplierErrorMessage, suppliersRequest, type Category, type Supplier } from "@/lib/suppliers";
import { track } from "@/lib/telemetry";

const dialogLoading = () => <div className="loading-state" role="status"><span className="spinner" />Cargando formulario…</div>;
const CreateSupplierDialog = dynamic(() => import("@/components/suppliers/CreateSupplierDialog"), { ssr: false, loading: dialogLoading });
const EditRateDialog = dynamic(() => import("@/components/suppliers/EditRateDialog"), { ssr: false, loading: dialogLoading });

function formatDate(value?: string): string {
  if (!value) return "Fecha no disponible";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? "Fecha no disponible" : date.toLocaleDateString("es-ES");
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
    const startedAt = performance.now();
    suppliersRequest<Supplier[]>("", { signal: controller.signal })
      .then((data) => {
        if (!isSupplierList(data)) throw new Error("El directorio devolvió una respuesta no válida. Inténtalo de nuevo.");
        setSuppliers(data);
        setError("");
        track("frontend_data_load_completed", {
          section: "suppliers",
          outcome: data.length ? "ready" : "empty",
          duration_ms: Math.round(performance.now() - startedAt),
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setError(supplierErrorMessage(error));
          track("frontend_data_load_completed", {
            section: "suppliers",
            outcome: "error",
            duration_ms: Math.round(performance.now() - startedAt),
          });
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function reload() {
    const startedAt = performance.now();
    setLoading(true); setError(""); setNotice("");
    try {
      const data = await suppliersRequest<Supplier[]>();
      if (!isSupplierList(data)) throw new Error("El directorio devolvió una respuesta no válida. Inténtalo de nuevo.");
      setSuppliers(data);
      track("frontend_data_load_completed", {
        section: "suppliers",
        outcome: data.length ? "ready" : "empty",
        duration_ms: Math.round(performance.now() - startedAt),
      });
    }
    catch (error) {
      setError(supplierErrorMessage(error));
      track("frontend_data_load_completed", {
        section: "suppliers",
        outcome: "error",
        duration_ms: Math.round(performance.now() - startedAt),
      });
    }
    finally { setLoading(false); }
  }

  async function toggleStatus(supplier: Supplier) {
    setPendingId(supplier.id); setError(""); setNotice("");
    try {
      const updated = await suppliersRequest<Supplier>(`/${supplier.id}/status`, { method: "PATCH", body: JSON.stringify({ status: supplier.status === "active" ? "suspended" : "active" }) });
      if (!isSupplier(updated)) throw new Error("El directorio devolvió un proveedor no válido. Inténtalo de nuevo.");
      setSuppliers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${supplier.name}: ${updated.status === "active" ? "activado" : "suspendido"}.`);
    } catch (error) { setError(supplierErrorMessage(error)); }
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

      {creating && <CreateSupplierDialog onClose={() => setCreating(false)} onCreated={(supplier) => { setSuppliers((current) => [...current, supplier]); setCountry(""); setCategory(""); setSearch(""); setCreating(false); setNotice(`${supplier.name} registrado.`); }} />}
      {editing && <EditRateDialog supplier={editing} onClose={() => setEditing(null)} onUpdated={(supplier) => { setSuppliers((current) => current.map((item) => item.id === supplier.id ? supplier : item)); setEditing(null); setNotice(`Tarifa de ${supplier.name} actualizada.`); }} />}
    </div>
  );
}