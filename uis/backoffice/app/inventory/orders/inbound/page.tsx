"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import {
  createAssetEntry,
  readableInventoryError,
} from "../../../../lib/inventory";
import { useInventoryAssets } from "../../../../hooks/useInventoryAssets";

export default function InboundOrderPage() {
  const { assets, setAssets, loading, error: loadError, retryLoading } = useInventoryAssets();
  const [assetId, setAssetId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [supplier, setSupplier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedAsset = useMemo(
    () => assets.find((asset) => String(asset.id) === assetId) ?? null,
    [assets, assetId],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setSuccess("");

    const parsedQuantity = Number(quantity);
    if (!selectedAsset) {
      setFormError("Selecciona un producto.");
      return;
    }
    if (!Number.isSafeInteger(parsedQuantity) || parsedQuantity < 1) {
      setFormError("La cantidad debe ser un entero mayor que cero.");
      return;
    }
    if (!supplier.trim()) {
      setFormError("Indica el proveedor de la entrada.");
      return;
    }

    setSubmitting(true);
    try {
      await createAssetEntry({
        asset_id: selectedAsset.id,
        quantity: parsedQuantity,
        supplier: supplier.trim(),
        office: selectedAsset.office,
      });
      setAssets((current) => current.map((asset) => asset.id === selectedAsset.id
        ? { ...asset, current_stock: asset.current_stock + parsedQuantity }
        : asset));
      setSuccess(`Entrada registrada: ${parsedQuantity} unidades de ${selectedAsset.name}.`);
      setAssetId("");
      setQuantity("1");
      setSupplier("");
    } catch (error) {
      setFormError(readableInventoryError(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="shell inventory-shell">
      <header className="hero inventory-hero">
        <div>
          <p className="badge">Nexova · Operaciones</p>
          <h1>Registrar entrada</h1>
          <p>Registra unidades recibidas y actualiza las existencias.</p>
        </div>
        <Link className="btn btn-outline" href="/inventory/products">Volver a productos</Link>
      </header>

      <section className="inventory-panel inbound-panel" aria-labelledby="inbound-title">
        <div className="panel-header inventory-panel-header">
          <div><p className="eyebrow">Nueva recepción</p><h2 id="inbound-title">Entrada de inventario</h2></div>
        </div>

        {loading && <div className="loading-state" role="status"><span className="spinner" /> Cargando productos…</div>}
        {!loading && loadError && <div className="empty-state inventory-error" role="alert"><span className="state-icon">!</span><h3>No se pudieron cargar los productos</h3><p>{loadError}</p><button className="btn btn-dark" type="button" onClick={retryLoading}>Reintentar</button></div>}
        {!loading && !loadError && assets.length === 0 && <div className="empty-state"><span className="state-icon">—</span><h3>No hay productos disponibles</h3><p>Registra un producto antes de crear una entrada.</p><Link className="btn btn-outline" href="/inventory/products">Ver productos</Link></div>}
        {!loading && !loadError && assets.length > 0 && <form className="inventory-entry-form" onSubmit={submit}>
          <label htmlFor="inbound-asset">Producto
            <select id="inbound-asset" required value={assetId} onChange={(event) => { setAssetId(event.target.value); setFormError(""); setSuccess(""); }}>
              <option value="">Selecciona un producto</option>
              {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.office} · {asset.sku}</option>)}
            </select>
          </label>

          {selectedAsset && <p className="inbound-stock">Stock actual: <strong>{selectedAsset.current_stock}</strong> · {selectedAsset.office}</p>}

          <div className="inbound-fields">
            <label htmlFor="inbound-quantity">Cantidad recibida
              <input id="inbound-quantity" type="number" min="1" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </label>
            <label htmlFor="inbound-supplier">Proveedor
              <input id="inbound-supplier" type="text" maxLength={200} required value={supplier} onChange={(event) => setSupplier(event.target.value)} />
            </label>
          </div>

          {formError && <p className="notice notice-error" role="alert">{formError}</p>}
          {success && <p className="notice notice-success" role="status">{success}</p>}

          <button className="btn btn-dark inbound-submit" type="submit" disabled={submitting || !selectedAsset}>
            {submitting ? "Guardando…" : "Registrar entrada"}
          </button>
        </form>}
      </section>
    </main>
  );
}