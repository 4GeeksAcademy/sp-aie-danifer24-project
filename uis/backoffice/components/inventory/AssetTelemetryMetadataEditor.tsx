"use client";

import { useEffect, useState } from "react";
import {
  listInventoryProgrammes,
  updateAssetTelemetryMetadata,
  type Asset,
  type InventoryBusinessCategory,
  type InventoryProgramme,
  readableInventoryError,
} from "../../lib/inventory";

const categories: { value: InventoryBusinessCategory; label: string }[] = [
  { value: "training_kit", label: "Kit de formación" },
  { value: "certification", label: "Certificación" },
  { value: "onboarding_equipment", label: "Equipo de incorporación" },
];

type Props = {
  asset: Asset;
  onSaved: (asset: Asset) => void;
};

export function AssetTelemetryMetadataEditor({ asset, onSaved }: Props) {
  const [productCategory, setProductCategory] = useState<InventoryBusinessCategory | "">(asset.product_category ?? "");
  const [programmeId, setProgrammeId] = useState(asset.programme_id ?? "");
  const [programmes, setProgrammes] = useState<InventoryProgramme[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    listInventoryProgrammes()
      .then((items) => { if (active) setProgrammes(items); })
      .catch((error: unknown) => { if (active) setCatalogError(readableInventoryError(error)); });
    return () => { active = false; };
  }, []);

  async function save() {
    if (!productCategory || !programmeId) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await updateAssetTelemetryMetadata(asset.id, {
        product_category: productCategory,
        programme_id: programmeId,
      });
      setMessage("Clasificación del producto guardada.");
      onSaved(updated);
    } catch (error) {
      setMessage(readableInventoryError(error));
    } finally {
      setSaving(false);
    }
  }

  const isSaved = asset.product_category === productCategory && asset.programme_id === programmeId;
  const hasOptions = !catalogError && programmes.length > 0;

  return (
    <fieldset className="inventory-product-classification">
      <legend>Clasificación del producto</legend>
      <p>Se define una vez para este producto y se reutiliza en sus movimientos.</p>
      <div className="inventory-classification-fields">
        <label htmlFor={`product-business-category-${asset.id}`}>Tipo de material
          <select
            id={`product-business-category-${asset.id}`}
            value={productCategory}
            onChange={(event) => setProductCategory(event.target.value as InventoryBusinessCategory | "")}
            required
          >
            <option value="">Selecciona una categoría</option>
            {categories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}
          </select>
        </label>
        <label htmlFor={`product-programme-${asset.id}`}>Programa o área
          <select
            id={`product-programme-${asset.id}`}
            value={programmeId}
            onChange={(event) => setProgrammeId(event.target.value)}
            required
            disabled={!hasOptions}
          >
            <option value="">{programmes.length ? "Selecciona un programa" : "Cargando programas…"}</option>
            {programmes.map((programme) => <option key={programme.id} value={programme.id}>{programme.name}</option>)}
          </select>
        </label>
      </div>
      {catalogError && <p className="notice notice-error" role="alert">No se pudo cargar el catálogo de programas: {catalogError}</p>}
      {!catalogError && !programmes.length && <p role="status">Cargando catálogo de programas…</p>}
      <button className="btn btn-outline" type="button" disabled={saving || !hasOptions || !productCategory || !programmeId || isSaved} onClick={save}>
        {saving ? "Guardando…" : isSaved ? "Clasificación guardada" : "Guardar clasificación"}
      </button>
      {message && <p role="status">{message}</p>}
    </fieldset>
  );
}