"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  createAssetEntry,
  listAssets,
  readableInventoryError,
  type Asset,
} from "../../../../lib/inventory";

function isAsset(value: unknown): value is Asset {
  if (!value || typeof value !== "object") return false;
  const asset = value as Partial<Asset>;
  return typeof asset.id === "number"
    && typeof asset.name === "string"
    && typeof asset.sku === "string"
    && (asset.office === "Valencia" || asset.office === "Miami")
    && typeof asset.current_stock === "number";
}

export default function InboundOrderPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  const [assetId, setAssetId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [supplier, setSupplier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;
    listAssets()
      .then((result) => {
        if (!Array.isArray(result) || !result.every(isAsset)) {
          throw new Error("El servicio devolvió una lista de productos no válida.");
        }
        if (active) setAssets(result);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(readableInventoryError(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [retry]);

  const selectedAsset = useMemo(
    () => assets.find((asset) => String(asset.id) === assetId) ?? null,
    [assets, assetId],
  );

  function retryLoading() {
    setLoadError("");
    setLoading(true);
    setRetry((current) => current + 1);
  }

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