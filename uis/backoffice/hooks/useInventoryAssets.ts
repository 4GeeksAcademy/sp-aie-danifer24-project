"use client";

import { useCallback, useEffect, useState } from "react";
import { listAssets, readableInventoryError, InventoryApiError, type Asset } from "../lib/inventory";
import { track } from "../lib/telemetry";

function isAsset(value: unknown): value is Asset {
  if (!value || typeof value !== "object") return false;
  const asset = value as Partial<Asset>;
  return typeof asset.id === "number"
    && Number.isFinite(asset.id)
    && typeof asset.name === "string"
    && typeof asset.sku === "string"
    && (asset.category === "hardware"
      || asset.category === "peripherals"
      || asset.category === "office_supplies"
      || asset.category === "training_materials")
    && (asset.office === "Valencia" || asset.office === "Miami")
    && (asset.product_category === null || asset.product_category === "training_kit" || asset.product_category === "certification" || asset.product_category === "onboarding_equipment")
    && (asset.programme_id === null || typeof asset.programme_id === "string")
    && typeof asset.current_stock === "number"
    && Number.isFinite(asset.current_stock);
}

export function useInventoryAssets() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    const startedAt = performance.now();
    const section = window.location.pathname === "/inventory/orders/inbound" ? "inventory_inbound" :
      window.location.pathname === "/inventory/orders/outbound" ? "inventory_outbound" : "inventory_products";

    listAssets()
      .then((result) => {
        if (!Array.isArray(result) || !result.every(isAsset)) {
          throw new Error("El servicio devolvió una lista de productos no válida.");
        }
        if (active) {
          setAssets(result);
          track("frontend_data_load_completed", {
            section,
            outcome: result.length ? "ready" : "empty",
            duration_ms: Math.round(performance.now() - startedAt),
          });
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(readableInventoryError(caught));
          track("frontend_data_load_completed", {
            section,
            outcome: "error",
            duration_ms: Math.round(performance.now() - startedAt),
            reason_code: caught instanceof InventoryApiError && (caught.status === 401 || caught.status === 403)
              ? "unauthorized"
              : caught instanceof InventoryApiError && caught.status !== undefined && caught.status >= 500
                ? "service_unavailable"
                : "network_error",
          });
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [retry]);

  const retryLoading = useCallback(() => {
    setError("");
    setLoading(true);
    setRetry((current) => current + 1);
  }, []);

  return { assets, setAssets, loading, error, retryLoading };
}