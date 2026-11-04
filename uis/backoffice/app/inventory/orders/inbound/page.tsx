"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  createAssetEntry,
  listInventorySuppliers,
  readableInventoryError,
} from "../../../../lib/inventory";
import type { Supplier } from "../../../../lib/suppliers";
import { useInventoryAssets } from "../../../../hooks/useInventoryAssets";
import { track } from "../../../../lib/telemetry";

export default function InboundOrderPage() {
  const { assets, setAssets, loading, error: loadError, retryLoading } = useInventoryAssets();
  const [assetId, setAssetId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [supplierId, setSupplierId] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierError, setSupplierError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedAsset = useMemo(
    () => assets.find((asset) => String(asset.id) === assetId) ?? null,
    [assets, assetId],
  );
  const matchingSuppliers = suppliers.filter((item) => item.status === "active"
    && item.currency === (selectedAsset?.office === "Valencia" ? "EUR" : "USD"));

  useEffect(() => {
    listInventorySuppliers().then(setSuppliers).catch(() => setSupplierError("No se pudieron cargar proveedores activos."));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setSuccess("");

    const parsedQuantity = Number(quantity);
    if (!selectedAsset) {
      track("inventory_order_validation_failed", { order_type: "inbound", layer: "frontend", field: "product_id", reason_code: "required" });
      setFormError("Selecciona un producto.");
      return;
    }
    if (!Number.isSafeInteger(parsedQuantity) || parsedQuantity < 1) {
      track("inventory_order_validation_failed", { order_type: "inbound", layer: "frontend", field: "quantity", reason_code: "out_of_range" });
      setFormError("La cantidad debe ser un entero mayor que cero.");
      return;
    }
    const selectedSupplier = matchingSuppliers.find((item) => String(item.id) === supplierId);
    if (!selectedSupplier) {
      track("inventory_order_validation_failed", { order_type: "inbound", layer: "frontend", field: "other", reason_code: "required" });
      setFormError("Selecciona un proveedor activo con moneda compatible con la oficina.");
      return;
    }
    const parsedUnitCost = Number(unitCost);
    if (!Number.isFinite(parsedUnitCost) || parsedUnitCost < 0) {
      setFormError("Indica un coste unitario válido (cero o mayor).");
      return;
    }
    if (!selectedAsset.product_category || !selectedAsset.programme_id) {
      setFormError("Guarda primero la categoría de negocio y el programa del producto.");
      return;
    }

    setSubmitting(true);
    try {
      const entry = await createAssetEntry({
        asset_id: selectedAsset.id,
        quantity: parsedQuantity,
        supplier_id: selectedSupplier.id,
        unit_cost: parsedUnitCost,
        office: selectedAsset.office,
      });
      track("inbound_order_created", {
        office: selectedAsset.office.toLowerCase(),
        product_id: selectedAsset.id,
        product_category: selectedAsset.product_category,
        programme_id: selectedAsset.programme_id,
        quantity: entry.quantity,
        currency: selectedSupplier.currency,
        order_id: entry.id,
        supplier_id: entry.supplier_id,
        unit_cost: entry.unit_cost,
      });
      setAssets((current) => current.map((asset) => asset.id === selectedAsset.id
        ? { ...asset, current_stock: asset.current_stock + parsedQuantity }
        : asset));
      setSuccess(`Entrada registrada: ${parsedQuantity} unidades de ${selectedAsset.name}.`);
      setAssetId("");
      setQuantity("1");
      setSupplierId("");
      setUnitCost("");
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
        {!loading && !loadError && assets.length > 0 && <form className="inventory-entry-form" onInvalidCapture={(event) => {
          const target = event.target;
          if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
          const field = target.id === "inbound-asset" ? "product_id" : target.id === "inbound-quantity" ? "quantity" : target.id === "inbound-supplier" ? "supplier_id" : "other";
          const reason_code = target.validity.valueMissing ? "required" : target.validity.badInput ? "invalid_type" : "out_of_range";
          track("inventory_order_validation_failed", { order_type: "inbound", layer: "browser", field, reason_code });
        }} onSubmit={submit}>
          <label htmlFor="inbound-asset">Producto
            <select id="inbound-asset" required value={assetId} onChange={(event) => { setAssetId(event.target.value); setFormError(""); setSuccess(""); }}>
              <option value="">Selecciona un producto</option>
              {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.office} · {asset.sku}</option>)}
            </select>
          </label>

          {selectedAsset && <p className="inbound-stock">Stock actual: <strong>{selectedAsset.current_stock}</strong> · {selectedAsset.office}</p>}

          {selectedAsset && (!selectedAsset.product_category || !selectedAsset.programme_id) && <p className="notice notice-error" role="status">
            Este producto no tiene clasificación. <Link href="/inventory/products">Asígnala en Productos</Link> antes de registrar movimientos.
          </p>}

          <div className="inbound-fields">
            <label htmlFor="inbound-quantity">Cantidad recibida
              <input id="inbound-quantity" type="number" min="1" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </label>
            <label htmlFor="inbound-supplier">Proveedor activo
              <select id="inbound-supplier" required value={supplierId} onChange={(event) => setSupplierId(event.target.value)}>
                <option value="">Selecciona un proveedor</option>
                {matchingSuppliers.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.currency}</option>)}
              </select>
            </label>
            <label htmlFor="inbound-unit-cost">Coste unitario ({selectedAsset?.office === "Valencia" ? "EUR" : "USD"})
              <input id="inbound-unit-cost" type="number" min="0" step="0.01" required value={unitCost} onChange={(event) => setUnitCost(event.target.value)} />
            </label>
          </div>
          {supplierError && <p className="notice notice-error" role="alert">{supplierError}</p>}

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