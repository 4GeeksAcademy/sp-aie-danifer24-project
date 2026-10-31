"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  listInventoryOrders,
  readableInventoryError,
  type InventoryOrder,
} from "../../../lib/inventory";

function isInventoryOrder(value: unknown): value is InventoryOrder {
  if (!value || typeof value !== "object") return false;
  const order = value as Partial<InventoryOrder>;
  const record = value as Record<string, unknown>;
  return typeof order.id === "number"
    && (order.order_type === "inbound" || order.order_type === "outbound")
    && typeof order.quantity === "number"
    && typeof order.created_at === "string"
    && typeof order.asset_name === "string"
    && typeof order.asset_sku === "string"
    && (order.order_type === "inbound"
      ? typeof record.supplier === "string"
      : (record.exit_type === "allocation" || record.exit_type === "consumption")
        && (typeof record.assigned_to === "string" || record.assigned_to === null));
}

function formatOrderDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function InventoryOrdersPage() {
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    listInventoryOrders()
      .then((result) => {
        if (!Array.isArray(result) || !result.every(isInventoryOrder)) {
          throw new Error("El servicio devolvió un historial de órdenes no válido.");
        }
        if (active) setOrders(result);
      })
      .catch((caught: unknown) => {
        if (active) setError(readableInventoryError(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [retry]);

  function retryLoading() {
    setError("");
    setLoading(true);
    setRetry((current) => current + 1);
  }

  return (
    <main className="shell inventory-shell">
      <header className="hero inventory-hero">
        <div>
          <p className="badge">Nexova · Operaciones</p>
          <h1>Historial de órdenes</h1>
          <p>Consulta las entradas y salidas registradas en el inventario.</p>
        </div>
        <Link className="btn btn-outline" href="/inventory/products">Volver a productos</Link>
      </header>

      <section className="inventory-panel" aria-labelledby="orders-title">
        <div className="panel-header inventory-panel-header">
          <div><p className="eyebrow">Movimientos</p><h2 id="orders-title">Órdenes registradas</h2></div>
          {!loading && !error && <span className="count-pill">{orders.length} {orders.length === 1 ? "orden" : "órdenes"}</span>}
        </div>

        {loading && <div className="loading-state" role="status"><span className="spinner" /> Cargando órdenes…</div>}
        {!loading && error && <div className="empty-state inventory-error" role="alert"><span className="state-icon">!</span><h3>No se pudo cargar el historial</h3><p>{error}</p><button className="btn btn-dark" type="button" onClick={retryLoading}>Reintentar</button></div>}
        {!loading && !error && orders.length === 0 && <div className="empty-state"><span className="state-icon">—</span><h3>Aún no hay órdenes</h3><p>Las entradas y salidas registradas aparecerán aquí.</p></div>}
        {!loading && !error && orders.length > 0 && <div className="inventory-table-wrap">
          <table className="inventory-table inventory-history-table">
            <thead><tr><th scope="col">Producto</th><th scope="col">Cantidad</th><th scope="col">Tipo de orden</th><th scope="col">Fecha de creación</th><th scope="col">Proveedor / destino</th></tr></thead>
            <tbody>{orders.map((order) => {
              const inbound = order.order_type === "inbound";
              return <tr key={`${order.order_type}-${order.id}`}>
                <th scope="row"><span className="inventory-product-name">{order.asset_name}</span><span className="inventory-sku">{order.asset_sku}</span></th>
                <td>{order.quantity}</td>
                <td><span className={`order-type-badge ${inbound ? "order-type-inbound" : "order-type-outbound"}`}><span aria-hidden="true">{inbound ? "+" : "−"}</span>{inbound ? "Entrada" : "Salida"}</span></td>
                <td><time dateTime={order.created_at}>{formatOrderDate(order.created_at)}</time></td>
                <td>{inbound ? order.supplier : order.assigned_to ?? "Consumo"}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
      </section>
    </main>
  );
}