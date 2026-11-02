"use client";

import { useState, type FormEvent } from "react";
import { AlertCircle, Plus } from "lucide-react";
import { categories, isSupplier, supplierErrorMessage, suppliersRequest, type Category, type Country, type Supplier, type SupplierInput } from "@/lib/suppliers";
import { SupplierModal } from "./SupplierModal";

export default function CreateSupplierDialog({ onClose, onCreated }: {
  onClose: () => void;
  onCreated: (supplier: Supplier) => void;
}) {
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
    } catch (error) { setError(supplierErrorMessage(error)); }
    finally { setBusy(false); }
  }

  return (
    <SupplierModal title="Nuevo proveedor" onClose={onClose} busy={busy}>
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
    </SupplierModal>
  );
}