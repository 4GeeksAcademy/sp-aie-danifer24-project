import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from services.api.models import Supplier, SupplierCreate


class SupplierModelsTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "name": "Workable",
            "country": "Spain",
            "categories": ["ats_software"],
            "monthly_rate": 299.0,
            "currency": "EUR",
            "status": "active",
        }

    def test_valid_input_and_response(self):
        request = SupplierCreate(**self.payload)
        self.assertNotIn("updated_at", request.model_dump())
        before = datetime.now(timezone.utc)
        supplier = Supplier(**request.model_dump())
        self.assertGreaterEqual(supplier.updated_at, before)
        self.assertLessEqual(supplier.updated_at, datetime.now(timezone.utc))
        self.assertEqual(supplier.updated_at.utcoffset().total_seconds(), 0)
        self.assertEqual(supplier.model_dump(mode="json")["status"], "active")

    def test_valid_usa_suspended_supplier(self):
        supplier = SupplierCreate(
            **{**self.payload, "country": "USA", "currency": "USD", "status": "suspended"}
        )
        self.assertEqual(supplier.status, "suspended")

    def test_invalid_rates(self):
        for rate in (0, -1, float("inf"), float("-inf"), float("nan"), "invalid", None):
            with self.subTest(rate=rate), self.assertRaises(ValidationError):
                SupplierCreate(**{**self.payload, "monthly_rate": rate})

    def test_invalid_domain_fields(self):
        invalid_fields = (
            {"status": "deleted"},
            {"status": "activo"},
            {"country": "France"},
            {"currency": "GBP"},
            {"currency": "USD"},
            {"country": "USA"},
            {"categories": []},
            {"categories": ["unknown"]},
            {"categories": ["ats_software", "unknown"]},
            {"name": "   "},
            {"contract_renewal_date": "2026-02-30"},
            {"contract_renewal_date": "05/10/2026"},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                SupplierCreate(**{**self.payload, **fields})

    def test_required_fields(self):
        for field in self.payload:
            payload = self.payload.copy()
            del payload[field]
            with self.subTest(field=field), self.assertRaises(ValidationError):
                SupplierCreate(**payload)

    def test_client_cannot_set_updated_at(self):
        with self.assertRaises(ValidationError):
            SupplierCreate(**self.payload, updated_at="2026-10-05T00:00:00Z")

    def test_optional_fields_and_stored_timestamp(self):
        timestamp = datetime(2026, 10, 5, tzinfo=timezone.utc)
        supplier = Supplier(
            **self.payload,
            updated_at=timestamp,
            contract_renewal_date="2026-11-01",
            contact_email="support@workable.com",
            notes="ATS principal",
        )
        restored = Supplier.model_validate_json(supplier.model_dump_json())
        self.assertEqual(restored, supplier)
        self.assertEqual(restored.updated_at, timestamp)


if __name__ == "__main__":
    unittest.main()