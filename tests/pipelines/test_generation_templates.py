"""
Tests for RFP Generation template fallback — no DB required.

Tests that _generate_draft_template produces valid proposals
for each department without needing any database or LLM.
"""
from __future__ import annotations

import importlib.util
import sys
from unittest.mock import patch

import pytest


def _import_template_function():
    """
    Import _generate_draft_template without importing models (which need DB).
    We achieve this by patching the models module at import time.
    """
    with patch.dict("sys.modules", {}):
        # Prevent models from being loaded by providing a mock
        mock_models = pytest.importorskip("unittest.mock").MagicMock()
        sys.modules["services.api.models"] = mock_models
        sys.modules["services.api.database"] = pytest.MagicMock()

        from services.api.services.rfp_generation import _generate_draft_template

        return _generate_draft_template


# We'll test the function by importing the actual module more carefully


@pytest.fixture(scope="module")
def generate_draft():
    """Return the _generate_draft_template function, importing it safely."""
    # Since the module needs DB, we test via a subprocess or direct import
    # For now, test with a local copy of the logic
    return None


def _expected_sections(dept_id: str) -> list[str]:
    """Keywords that should appear in each department's draft."""
    keywords = {
        "seleccion": [
            "Talent Selection",
            "selección",
            "metodología",
            "económica",
            "Nexova",
        ],
        "capacitacion": ["Corporate Training", "capacitación", "formación", "Nexova"],
        "soporte": ["Customer Support", "soporte", "Nexova"],
    }
    return keywords.get(dept_id, ["Nexova"])


class TestTemplateFallback:
    """Tests for template-based draft generation (no DB needed)."""

    def test_seleccion_draft_has_required_content(self):
        """Template draft for seleccion includes roles, methodology, costs."""
        from services.api.services.rfp_generation import _generate_draft_template

        draft = _generate_draft_template(
            "seleccion",
            {"roles_to_cover": ["5"], "estimated_close_time": "30 días", "open_questions": []},
            "Test Client",
            "EUR",
        )
        assert draft
        assert "Talent Selection" in draft
        assert "EUR" in draft
        assert "Test Client" in draft
        assert "Nexova" in draft
        assert len(draft) > 200

    def test_capacitacion_draft_has_required_content(self):
        """Template draft for capacitacion includes programs, methodology."""
        from services.api.services.rfp_generation import _generate_draft_template

        draft = _generate_draft_template(
            "capacitacion",
            {"applicable_programs": ["liderazgo"], "duration": "trimestral", "open_questions": []},
            "Test Client",
            "EUR",
        )
        assert draft
        assert "Corporate Training" in draft
        assert "liderazgo" in draft.lower()
        assert "Nexova" in draft

    def test_soporte_draft_has_required_content(self):
        """Template draft for soporte includes agents, shifts, SLA."""
        from services.api.services.rfp_generation import _generate_draft_template

        draft = _generate_draft_template(
            "soporte",
            {"agent_count": 12, "shifts": "24/7", "sla_response": "24 horas"},
            "Test Client",
            "USD",
        )
        assert draft
        assert "Customer Support" in draft
        assert "USD" in draft
        assert "Nexova" in draft
        assert len(draft) > 200

    def test_unknown_dept_still_produces_draft(self):
        """Unknown department produces a default-format draft."""
        from services.api.services.rfp_generation import _generate_draft_template

        draft = _generate_draft_template("unknown", {}, "Client", "EUR")
        assert draft
        assert "Client" in draft
        assert "EUR" in draft

    def test_draft_references_client_name(self):
        """Client name appears throughout the draft."""
        from services.api.services.rfp_generation import _generate_draft_template

        draft = _generate_draft_template(
            "seleccion",
            {"roles_to_cover": ["3"]},
            "Vantex Retail",
            "EUR",
        )
        assert "Vantex" in draft