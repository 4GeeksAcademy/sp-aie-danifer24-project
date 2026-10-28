"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  createAssetExit,
  getAsset,
  listAssets,
  readableInventoryError,
  InventoryApiError,
  type Asset,
  type AssetExitInput,
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

export default function OutboundOrderPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  const [assetId, setAssetId] = useState("");
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [stockError, setStockError] = useState("");
  const [quantity, setQuantity] = useState("");
  const [exitType, setExitType] = useState<AssetExitInput["exit_type"]>("allocation");
  const [assignedTo, setAssignedTo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [quantityError, setQuantityError] = useState("");
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const stockRequestId = useRef(0);

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

  useEffect(() => () => { stockRequestId.current += 1; }, []);

  function retryLoading() {
    setLoadError("");
    setLoading(true);
    setRetry((current) => current + 1);
  }

  function selectAsset(value: string) {
    const requestId = ++stockRequestId.current;
    setAssetId(value);
    setSelectedAsset(null);
    setQuantity("");
    setStockError("");
    setQuantityError("");
    setFormError("");
    setSuccess("");
    setStockLoading(Boolean(value));
    if (!value) return;

    getAsset(Number(value))
      .then((asset) => {
        if (stockRequestId.current === requestId) setSelectedAsset(asset);
      })
      .catch((error: unknown) => {
        if (stockRequestId.current === requestId) setStockError(readableInventoryError(error));
      })
      .finally(() => {
        if (stockRequestId.current === requestId) setStockLoading(false);
      });
  }

  const parsedQuantity = Number(quantity);
  const quantityExceedsStock = selectedAsset !== null
    && quantity !== ""
    && Number.isSafeInteger(parsedQuantity)
    && parsedQuantity > selectedAsset.current_stock;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuantityError("");
    setFormError("");
    setSuccess("");

    if (!selectedAsset) {
      setFormError("Selecciona un producto y espera a que se consulte su stock.");
      return;
    }
    if (!Number.isSafeInteger(parsedQuantity) || parsedQuantity < 1) {
      setQuantityError("La cantidad debe ser un entero mayor que cero.");
      return;
    }
    if (exitType === "allocation" && !assignedTo.trim()) {
      setFormError("Indica a quién se asignará el producto.");
      return;
    }

    setSubmitting(true);
    try {
      await createAssetExit({
        asset_id: selectedAsset.id,
        quantity: parsedQuantity,
        exit_type: exitType,
        assigned_to: exitType === "allocation" ? assignedTo.trim() : null,
        office: selectedAsset.office,
      });
      const newStock = selectedAsset.current_stock - parsedQuantity;
      setSelectedAsset({ ...selectedAsset, current_stock: newStock });
      setAssets((current) => current.map((asset) => asset.id === selectedAsset.id
        ? { ...asset, current_stock: newStock }
        : asset));
      setSuccess(`Salida registrada: ${parsedQuantity} unidades de ${selectedAsset.name}.`);
      setQuantity("");
      setAssignedTo("");
    } catch (error) {
      if (error instanceof InventoryApiError && error.status === 400) {
        setQuantityError(readableInventoryError(error));
      } else {
        setFormError(readableInventoryError(error));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="shell inventory-shell">
      <header className="hero inventory-hero">
        <div>
          <p className="badge">Nexova · Operaciones</p>
          <h1>Registrar salida</h1>
          <p>Consulta el stock antes de asignar o consumir unidades.</p>
        </div>
        <Link className="btn btn-outline" href="/inventory/products">Volver a productos</Link>
      </header>

      <section className="inventory-panel outbound-panel" aria-labelledby="outbound-title">
        <div className="panel-header inventory-panel-header">
          <div><p className="eyebrow">Nueva salida</p><h2 id="outbound-title">Salida de inventario</h2></div>
        </div>

        {loading && <div className="loading-state" role="status"><span className="spinner" /> Cargando productos…</div>}
        {!loading && loadError && <div className="empty-state inventory-error" role="alert"><span className="state-icon">!</span><h3>No se pudieron cargar los productos</h3><p>{loadError}</p><button className="btn btn-dark" type="button" onClick={retryLoading}>Reintentar</button></div>}
        {!loading && !loadError && assets.length === 0 && <div className="empty-state"><span className="state-icon">—</span><h3>No hay productos disponibles</h3><p>Registra un producto antes de crear una salida.</p><Link className="btn btn-outline" href="/inventory/products">Ver productos</Link></div>}
        {!loading && !loadError && assets.length > 0 && <form className="inventory-order-page-form" onSubmit={submit}>
          <label htmlFor="outbound-asset">Producto
            <select id="outbound-asset" required value={assetId} onChange={(event) => selectAsset(event.target.value)}>
              <option value="">Selecciona un producto</option>
              {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.office} · {asset.sku}</option>)}
            </select>
          </label>

          {stockLoading && <p className="inbound-stock" role="status"><span className="spinner" /> Consultando stock…</p>}
          {!stockLoading && stockError && <p className="notice notice-error" role="alert">{stockError}</p>}
          {selectedAsset && !stockLoading && <p className="inbound-stock">Stock disponible: <strong>{selectedAsset.current_stock}</strong> · {selectedAsset.office}</p>}

          <label htmlFor="outbound-quantity">Cantidad
            <input id="outbound-quantity" type="number" min="1" step="1" required disabled={!selectedAsset || stockLoading} value={quantity} aria-invalid={Boolean(quantityError || quantityExceedsStock)} aria-describedby={quantityError ? "outbound-quantity-error" : quantityExceedsStock ? "outbound-stock-warning" : undefined} onChange={(event) => { setQuantity(event.target.value); setQuantityError(""); setFormError(""); setSuccess(""); }} />
          </label>
          {quantityError && <p className="field-error" id="outbound-quantity-error" role="alert">{quantityError}</p>}
          {quantityExceedsStock && <p className="inventory-stock-warning" id="outbound-stock-warning" role="status">La cantidad supera el stock disponible ({selectedAsset.current_stock}). La API volverá a validarlo al enviar.</p>}

          <label htmlFor="outbound-type">Tipo de salida
            <select id="outbound-type" value={exitType} onChange={(event) => { setExitType(event.target.value as AssetExitInput["exit_type"]); setAssignedTo(""); setFormError(""); }}>
              <option value="allocation">Asignación</option><option value="consumption">Consumo</option>
            </select>
          </label>
          {exitType === "allocation" && <label htmlFor="outbound-assigned-to">Asignado a
            <input id="outbound-assigned-to" type="text" maxLength={200} required value={assignedTo} onChange={(event) => { setAssignedTo(event.target.value); setFormError(""); }} />
          </label>}

          {formError && <p className="notice notice-error" role="alert">{formError}</p>}
          {success && <p className="notice notice-success" role="status">{success}</p>}
          <button className="btn btn-dark inbound-submit" type="submit" disabled={submitting || stockLoading || !selectedAsset}>
            {submitting ? "Guardando…" : "Registrar salida"}
          </button>
        </form>}
      </section>
    </main>
  );
}