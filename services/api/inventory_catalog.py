"""Academic reference catalog for the inventory telemetry exercise."""

BUSINESS_PRODUCT_CATEGORIES = {
	"training_kit": "Kit de formación",
	"certification": "Material de certificación",
	"onboarding_equipment": "Equipo de incorporación",
}

INVENTORY_PROGRAMMES = (
	{"id": "ventas-b2b", "name": "Formación en ventas B2B"},
	{"id": "liderazgo-basico", "name": "Liderazgo básico"},
	{"id": "onboarding-soporte", "name": "Onboarding de soporte"},
)

INVENTORY_PROGRAMME_IDS = tuple(programme["id"] for programme in INVENTORY_PROGRAMMES)