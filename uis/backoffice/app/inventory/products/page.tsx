"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listAssets, readableInventoryError, type Asset } from "../../../lib/inventory";

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

      <section className="inventory-panel" aria-labelledby="products-title">
        <div className="panel-header inventory-panel-header">
          <div><p className="eyebrow">Existencias</p><h2 id="products-title">Productos</h2></div>
          {!loading && !error && <div className="inventory-panel-tools">
            <span className="count-pill">{filteredAssets.length} {filteredAssets.length === 1 ? "producto" : "productos"}</span>
            {assets.length > 0 && <div className="inventory-page-actions">
              <Link className="btn btn-outline" href="/inventory/orders">Historial de órdenes</Link>
              <Link className="btn btn-outline" href="/inventory/orders/inbound">Registrar entrada</Link>
              <Link className="btn btn-dark" href="/inventory/orders/outbound">Registrar salida</Link>
            </div>}
          </div>}
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
              <thead><tr><th scope="col">Producto</th><th scope="col">Categoría</th><th scope="col">Oficina</th><th scope="col">Stock actual</th></tr></thead>
              <tbody>{filteredAssets.map((asset) => {
                const state = stockState(asset.current_stock);
                return <tr key={asset.id}>
                  <th scope="row"><span className="inventory-product-name">{asset.name}</span><span className="inventory-sku">{asset.sku}</span></th>
                  <td>{CATEGORY_LABELS[asset.category] ?? asset.category}</td>
                  <td>{asset.office}</td>
                  <td><span className={`stock-indicator ${state.className}`}><span aria-hidden="true">{state.symbol}</span><strong>{asset.current_stock}</strong><span>{state.label}</span></span></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </section>

    </main>
  );
}