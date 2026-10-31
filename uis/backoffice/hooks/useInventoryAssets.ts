"use client";

import { useCallback, useEffect, useState } from "react";
import { listAssets, readableInventoryError, type Asset } from "../lib/inventory";

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

  const retryLoading = useCallback(() => {
    setError("");
    setLoading(true);
    setRetry((current) => current + 1);
  }, []);

  return { assets, setAssets, loading, error, retryLoading };
}