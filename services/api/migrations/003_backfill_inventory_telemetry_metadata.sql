-- Academic/demo seed data only: classify products by their exact seeded SKU and
-- identity. Do not infer business classifications from the technical category.
-- This migration is prepared locally and must be explicitly approved before
-- applying it to any remote database.
UPDATE asset
SET product_category = 'onboarding_equipment', programme_id = 'onboarding-soporte'
WHERE sku IN ('NXV-IT-001', 'NXV-IT-002', 'NXV-PER-001', 'NXV-PER-002')
;

UPDATE asset
SET product_category = 'training_kit', programme_id = 'liderazgo-basico'
WHERE sku IN ('NXV-OFF-001', 'NXV-TRN-001')
;

-- Existing assets with other SKUs (including certification materials) are
-- intentionally left untouched for manual classification.