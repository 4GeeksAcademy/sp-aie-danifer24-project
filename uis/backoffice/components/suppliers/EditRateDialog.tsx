"use client";

import { useState, type FormEvent } from "react";
import { AlertCircle, Check } from "lucide-react";
import { isSupplier, supplierErrorMessage, suppliersRequest, type Supplier } from "@/lib/suppliers";
import { SupplierModal } from "./SupplierModal";

export default function EditRateDialog({ supplier, onClose, onUpdated }: {
  supplier: Supplier;
  onClose: () => void;
  onUpdated: (supplier: Supplier) => void;
}) {
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
    } catch (error) { setError(supplierErrorMessage(error)); }
    finally { setBusy(false); }
  }

  return (
    <SupplierModal title="Actualizar tarifa" onClose={onClose} busy={busy}>
      <p className="modal-supplier-name">{supplier.name}</p>
      <form onSubmit={submit}>
        <label>Tarifa mensual ({supplier.currency})<input name="monthly_rate" type="number" min="0.01" step="0.01" required defaultValue={supplier.monthly_rate} autoFocus disabled={busy} inputMode="decimal" /></label>
        {error && <p className="error-message" role="alert"><AlertCircle size={18} />{error}</p>}
        <footer className="modal-footer"><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancelar</button><button className="primary-button" disabled={busy}><Check size={17} />{busy ? "Guardando…" : "Guardar tarifa"}</button></footer>
      </form>
    </SupplierModal>
  );
}