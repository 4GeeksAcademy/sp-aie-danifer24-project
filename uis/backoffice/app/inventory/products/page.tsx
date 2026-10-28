"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  createAssetEntry,
  createAssetExit,
  listAssets,
  readableInventoryError,
  type Asset,
  type AssetExitInput,
} from "../../../lib/inventory";

type OrderType = "inbound" | "outbound";

const CATEGORY_LABELS: Record<Asset["category"], string> = {
  hardware: "Hardware",
  peripherals: "Periféricos",
  office_supplies: "Material de oficina",
  training_materials: "Material de formación",
};

// Stock saludable: 5 unidades o más; bajo: de 1 a 4; sin stock: 0.
const LOW_STOCK_THRESHOLD = 5;

function isAsset(value: unknown): value is Asset {
  if (!value || typeof value !== "object") return false;
  const asset = value as Partial<Asset>;
  return typeof asset.id === "number"
    && typeof asset.name === "string"
    && typeof asset.sku === "string"
    && typeof asset.category === "string"
    && typeof asset.office === "string"
    && typeof asset.current_stock === "number"
    && Number.isFinite(asset.current_stock);
}

function stockState(stock: number): { label: string; className: string; symbol: string } {
  if (stock <= 0) return { label: "Sin stock", className: "stock-empty", symbol: "!" };
  if (stock < LOW_STOCK_THRESHOLD) return { label: "Stock bajo", className: "stock-low", symbol: "!" };
  return { label: "Saludable", className: "stock-healthy", symbol: "✓" };
}

export default function InventoryProductsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState("");
  const [orderType, setOrderType] = useState<OrderType | null>(null);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [supplier, setSupplier] = useState("");
  const [exitType, setExitType] = useState<AssetExitInput["exit_type"]>("allocation");
  const [assignedTo, setAssignedTo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    listAssets()
      .then((result) => {
        if (!Array.isArray(result) || !result.every(isAsset)) {
          throw new Error("El servicio devolvió una lista de productos no válida.");
        }
        if (active) setAssets(result);
      })
      .catch((caught: unknown) => {
        if (active) setError(readableInventoryError(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [retry]);

  const filteredAssets = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("es");
    if (!term) return assets;
    return assets.filter((asset) => [asset.name, asset.sku, asset.office, CATEGORY_LABELS[asset.category]]
      .some((value) => value.toLocaleLowerCase("es").includes(term)));
  }, [assets, search]);

  const totalUnits = assets.reduce((total, asset) => total + asset.current_stock, 0);
  const lowStockCount = assets.filter((asset) => asset.current_stock < LOW_STOCK_THRESHOLD).length;

  function openOrder(asset: Asset, type: OrderType) {
    setSelectedAsset(asset);
    setOrderType(type);
    setQuantity("1");
    setSupplier("");
    setExitType("allocation");
    setAssignedTo("");
    setFormError("");
    setNotice("");
  }

  function closeOrder() {
    if (submitting) return;
    setOrderType(null);
    setSelectedAsset(null);
    setFormError("");
  }

  async function submitOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAsset || !orderType) return;
    const parsedQuantity = Number(quantity);
    if (!Number.isSafeInteger(parsedQuantity) || parsedQuantity < 1) {
      setFormError("Indica una cantidad entera mayor que cero.");
      return;
    }

    setSubmitting(true);
    setFormError("");
    setNotice("");
    try {
      if (orderType === "inbound") {
        await createAssetEntry({
          asset_id: selectedAsset.id,
          quantity: parsedQuantity,
          supplier: supplier.trim(),
          office: selectedAsset.office,
        });
        setAssets((current) => current.map((asset) => asset.id === selectedAsset.id
          ? { ...asset, current_stock: asset.current_stock + parsedQuantity }
          : asset));
        setNotice(`Entrada registrada para ${selectedAsset.name}.`);
      } else {
        await createAssetExit({
          asset_id: selectedAsset.id,
          quantity: parsedQuantity,
          exit_type: exitType,
          assigned_to: exitType === "allocation" ? assignedTo.trim() : null,
          office: selectedAsset.office,
        });
        setAssets((current) => current.map((asset) => asset.id === selectedAsset.id
          ? { ...asset, current_stock: asset.current_stock - parsedQuantity }
          : asset));
        setNotice(`Salida registrada para ${selectedAsset.name}.`);
      }
      setOrderType(null);
      setSelectedAsset(null);
    } catch (caught) {
      setFormError(readableInventoryError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="shell inventory-shell">
      <header className="hero inventory-hero">
        <div>
          <p className="badge">Nexova · Operaciones</p>
          <h1>Inventario de activos</h1>
          <p>Consulta existencias y registra entradas o salidas.</p>
        </div>
      </header>

      <section className="inventory-overview" aria-label="Resumen de inventario">
        <div><span>Productos</span><strong>{assets.length}</strong></div>
        <div><span>Unidades disponibles</span><strong>{totalUnits}</strong></div>
        <div className={lowStockCount > 0 ? "overview-warning" : ""}><span>Con stock bajo o agotado</span><strong>{lowStockCount}</strong></div>
      </section>

      {notice && <p className="notice notice-success" role="status">{notice}</p>}

      <section className="inventory-panel" aria-labelledby="products-title">
        <div className="panel-header inventory-panel-header">
          <div><p className="eyebrow">Existencias</p><h2 id="products-title">Productos</h2></div>
          {!loading && !error && <span className="count-pill">{filteredAssets.length} {filteredAssets.length === 1 ? "producto" : "productos"}</span>}
        </div>

        <label className="inventory-search" htmlFor="inventory-search">Buscar producto
          <input id="inventory-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre, SKU, categoría u oficina" />
        </label>

        {loading && <div className="loading-state" role="status"><span className="spinner" /> Cargando productos…</div>}
        {!loading && error && <div className="empty-state inventory-error" role="alert"><span className="state-icon">!</span><h3>No se pudieron cargar los productos</h3><p>{error}</p><button className="btn btn-dark" type="button" onClick={() => { setError(""); setLoading(true); setRetry((value) => value + 1); }}>Reintentar</button></div>}
        {!loading && !error && assets.length === 0 && <div className="empty-state"><span className="state-icon">—</span><h3>Aún no hay productos</h3><p>Los activos aparecerán aquí cuando se registren.</p></div>}
        {!loading && !error && assets.length > 0 && filteredAssets.length === 0 && <div className="empty-state"><h3>No hay coincidencias</h3><p>Prueba otra búsqueda.</p></div>}
        {!loading && !error && filteredAssets.length > 0 && (
          <div className="inventory-table-wrap">
            <table className="inventory-table">
              <thead><tr><th scope="col">Producto</th><th scope="col">Categoría</th><th scope="col">Oficina</th><th scope="col">Stock actual</th><th scope="col">Órdenes</th></tr></thead>
              <tbody>{filteredAssets.map((asset) => {
                const state = stockState(asset.current_stock);
                return <tr key={asset.id}>
                  <th scope="row"><span className="inventory-product-name">{asset.name}</span><span className="inventory-sku">{asset.sku}</span></th>
                  <td>{CATEGORY_LABELS[asset.category] ?? asset.category}</td>
                  <td>{asset.office}</td>
                  <td><span className={`stock-indicator ${state.className}`}><span aria-hidden="true">{state.symbol}</span><strong>{asset.current_stock}</strong><span>{state.label}</span></span></td>
                  <td><div className="inventory-row-actions">
                    <button className="btn btn-outline" type="button" onClick={() => openOrder(asset, "inbound")}>Registrar entrada</button>
                    <button className="btn btn-dark" type="button" disabled={asset.current_stock === 0} title={asset.current_stock === 0 ? "No hay unidades disponibles" : undefined} onClick={() => openOrder(asset, "outbound")}>Registrar salida</button>
                  </div></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </section>

      {orderType && selectedAsset && <div className="inventory-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeOrder(); }}>
        <section className="inventory-dialog" role="dialog" aria-modal="true" aria-labelledby="order-dialog-title">
          <div className="inventory-dialog-heading"><div><p className="eyebrow">{selectedAsset.sku} · {selectedAsset.office}</p><h2 id="order-dialog-title">{orderType === "inbound" ? "Registrar entrada" : "Registrar salida"}</h2><p>{selectedAsset.name}</p></div><button className="inventory-dialog-close" type="button" aria-label="Cerrar" disabled={submitting} onClick={closeOrder}>×</button></div>
          <form className="inventory-order-form" onSubmit={submitOrder}>
            <label htmlFor="order-quantity">Cantidad
              <input id="order-quantity" type="number" min="1" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </label>
            {orderType === "inbound" ? <label htmlFor="order-supplier">Proveedor
              <input id="order-supplier" type="text" required maxLength={200} value={supplier} onChange={(event) => setSupplier(event.target.value)} />
            </label> : <>
              <label htmlFor="order-exit-type">Tipo de salida
                <select id="order-exit-type" value={exitType} onChange={(event) => { setExitType(event.target.value as AssetExitInput["exit_type"]); setAssignedTo(""); }}>
                  <option value="allocation">Asignación</option><option value="consumption">Consumo</option>
                </select>
              </label>
              {exitType === "allocation" && <label htmlFor="order-assigned-to">Asignado a
                <input id="order-assigned-to" type="text" required maxLength={200} value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)} />
              </label>}
            </>}
            {formError && <p className="notice notice-error" role="alert">{formError}</p>}
            <div className="inventory-dialog-actions"><button className="btn btn-outline" type="button" disabled={submitting} onClick={closeOrder}>Cancelar</button><button className="btn btn-dark" type="submit" disabled={submitting}>{submitting ? "Guardando…" : orderType === "inbound" ? "Guardar entrada" : "Guardar salida"}</button></div>
          </form>
        </section>
      </div>}
    </main>
  );
}