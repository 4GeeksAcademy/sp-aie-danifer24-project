-- Add business metadata required by inbound/outbound telemetry.
-- Existing inventory history remains intact; legacy entries keep NULL supplier_id/unit_cost.
ALTER TABLE asset
    ADD COLUMN IF NOT EXISTS product_category TEXT,
    ADD COLUMN IF NOT EXISTS programme_id TEXT;

ALTER TABLE assetentry
    ADD COLUMN IF NOT EXISTS supplier_id INTEGER,
    ADD COLUMN IF NOT EXISTS unit_cost DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_product_category_check') THEN
        ALTER TABLE asset ADD CONSTRAINT asset_product_category_check
            CHECK (product_category IS NULL OR product_category IN ('training_kit', 'certification', 'onboarding_equipment'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'asset_programme_id_check') THEN
        ALTER TABLE asset ADD CONSTRAINT asset_programme_id_check
            CHECK (programme_id IS NULL OR programme_id ~ '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'assetentry_unit_cost_check') THEN
        ALTER TABLE assetentry ADD CONSTRAINT assetentry_unit_cost_check
            CHECK (unit_cost IS NULL OR unit_cost >= 0);
    END IF;
END $$;