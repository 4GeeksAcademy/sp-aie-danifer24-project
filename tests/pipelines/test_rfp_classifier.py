"""Unit tests for the RFP classifier agent (heuristic + LLM stubs).

Tests the classifier logic directly: _heuristic_classify (always testable)
and _llm_classify (with mocked OpenAI). Also tests full classify_rfp node.

Run with: uv run pytest tests/pipelines/test_rfp_classifier.py -q -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── ensure the services package is importable ────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "services"))

from api.services.rfp_intake import (
    _heuristic_classify,
    _llm_classify,
    classify_rfp,
    RFPIntakeState,
)


# ═══════════════════════════════════════════════════════════════════════
#  Fixtures: simulated document texts matching CONTEXT.md §4
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def rfp_formal_vantex() -> str:
    """nexova-request-1.pdf — formal RFP from Vantex Retail Group (Madrid)."""
    return """SOLICITUD DE PROPUESTA — NEXOVA

**Cliente:** Vantex Retail Group
**Sede:** Madrid, España
**Fecha:** 15/03/2025

Estimados en Nexova,

Por medio de la presente, Vantex Retail Group solicita una propuesta de servicios de outsourcing
de selección de personal y capacitación corporativa para nuestro equipo directivo.

Servicios solicitados:
1. Búsqueda ejecutiva de 5 mandos medios para nuestras oficinas en Madrid
2. Programa trimestral de liderazgo para los nuevos mandos

Requerimos:
- Headhunting de perfiles con experiencia en retail
- Formación en liderazgo y gestión de equipos
- Proceso de selección con evaluación psicométrica

Presupuesto de referencia: 45.000 EUR
Fecha límite para propuesta: 30/04/2025

Quedamos atentos a su propuesta.
Atentamente,
Laura Méndez
Directora de Recursos Humanos, Vantex Retail Group
"""


@pytest.fixture
def rfp_informal_nubefast() -> str:
    """nexova-request-2.pdf — informal RFP (email) from NubeSoft (Miami)."""
    return """De: Carolina Ruiz <caruiz@nubesoft.com>
Para: Marcos Ibáñez <marcos@nexova.com>
Asunto: Solicitud de propuesta — equipo de soporte

Hola Marcos,

Tal como hablamos, en NubeSoft estamos buscando un equipo de soporte al cliente 24/7
para nuestra plataforma SaaS. Necesitamos:

- 12 agentes bilingües (inglés/español)
- Cobertura 24/7 incluyendo fines de semana
- SLA de respuesta en menos de 24 horas
- Gestión de tickets en Zendesk

También necesitaremos apoyo en selección de los agentes antes del arranque.

Nuestra oficina principal está en Miami, FL.

¿Pueden prepararnos una propuesta?

Saludos,
Carolina Ruiz
VP Customer Experience, NubeSoft
"""


@pytest.fixture
def vendor_pitch_invalid() -> str:
    """nexova-request-3.pdf — invalid vendor pitch, NOT a client RFP."""
    return """Somos TalentMatch Solutions, una plataforma líder de ATS (Applicant Tracking System)
para empresas de outsourcing. Nuestro producto ofrece:

- Gestión automatizada de candidatos
- IA para matching de perfiles
- Integración con LinkedIn y portales de empleo
- Reportes en tiempo real

Más de 200 empresas confían en nosotros. Solicite una demo hoy.

Ofrecemos precios competitivos para empresas como Nexova.
Contáctenos para una demostración personalizada.

www.talentmatch-solutions.com
"""


@pytest.fixture
def short_empty_doc() -> str:
    """Very short text — should be rejected by heuristic."""
    return "Hola, esto es una prueba."


# ═══════════════════════════════════════════════════════════════════════
#  Heuristic classifier tests (always run, no API key needed)
# ═══════════════════════════════════════════════════════════════════════


class TestHeuristicClassifier:
    """Test the fallback keyword-based classifier."""

    def test_valid_formal_rfp(self, rfp_formal_vantex):
        result = _heuristic_classify(rfp_formal_vantex)
        assert result["is_valid_rfp"] is True, (
            f"Formal RFP should be classified as valid, got: {result}"
        )

    def test_valid_informal_rfp(self, rfp_informal_nubefast):
        result = _heuristic_classify(rfp_informal_nubefast)
        assert result["is_valid_rfp"] is True, (
            f"Informal email RFP should be classified as valid, got: {result}"
        )

    def test_invalid_vendor_pitch(self, vendor_pitch_invalid):
        result = _heuristic_classify(vendor_pitch_invalid)
        assert result["is_valid_rfp"] is False, (
            f"Vendor pitch should be rejected, got: {result}"
        )
        assert "pitch" in result.get("classification_reason", "").lower(), (
            f"Reason should mention pitch: {result}"
        )

    def test_short_empty_document(self, short_empty_doc):
        result = _heuristic_classify(short_empty_doc)
        assert result["is_valid_rfp"] is False, (
            f"Short text should be rejected, got: {result}"
        )
        assert "señales" in result.get("classification_reason", "").lower() or \
               "no se detect" in result.get("classification_reason", "").lower(), (
            f"Reason should mention no signals: {result}"
        )


# ═══════════════════════════════════════════════════════════════════════
#  LLM classifier tests (mocked)
# ═══════════════════════════════════════════════════════════════════════


class FakeResponse:
    """Minimal OpenAI ChatCompletion response stub."""

    def __init__(self, content: str):
        self.choices = [FakeChoice(content)]


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


def _mock_openai_chat(*, model, messages, temperature, **kwargs):
    """Return a fake valid-RFP response."""
    return FakeResponse(
        json.dumps({
            "is_valid_rfp": True,
            "reason": "Documento contiene solicitud explícita de servicios de outsourcing (selección de personal y capacitación). Cliente: Vantex Retail Group.",
        })
    )


def _mock_openai_invalid(*, model, messages, temperature, **kwargs):
    """Return a fake invalid (vendor pitch) response."""
    return FakeResponse(
        json.dumps({
            "is_valid_rfp": False,
            "reason": "Documento es un pitch de ventas de un proveedor de ATS, no una solicitud de cliente.",
        })
    )


class TestLLMClassifier:
    """Test LLM classifier path with mocked OpenAI."""

    def test_valid_formal_with_openai(self, rfp_formal_vantex):
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
            patch("openai.OpenAI") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = _mock_openai_chat
            result = _llm_classify(rfp_formal_vantex)
        assert result is not None
        assert result["is_valid_rfp"] is True

    def test_invalid_with_openai(self, vendor_pitch_invalid):
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
            patch("openai.OpenAI") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = _mock_openai_invalid
            result = _llm_classify(vendor_pitch_invalid)
        assert result is not None
        assert result["is_valid_rfp"] is False

    def test_llm_fallback_on_failure(self, rfp_formal_vantex):
        """When LLM raises, _llm_classify returns None (caller falls back to heuristic)."""
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
            patch("openai.OpenAI") as mock_client,
        ):
            mock_client.return_value.chat.completions.create.side_effect = Exception("API error")
            result = _llm_classify(rfp_formal_vantex)
        assert result is None, "Should return None on LLM failure"

    def test_no_api_key_returns_none(self, rfp_formal_vantex):
        with patch.dict("os.environ", clear=True):
            result = _llm_classify(rfp_formal_vantex)
        assert result is None, "Should return None when OPENAI_API_KEY is unset"

    def test_llm_json_in_markdown_fence(self, rfp_formal_vantex):
        """LLM may wrap JSON in ```markdown code fences -- parser must handle it."""
        import os
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
            patch("openai.OpenAI") as mock_client,
        ):

            def _fenced(*, model, messages, temperature, **kwargs):
                return FakeResponse(
                    "```json\n{\"is_valid_rfp\": true, \"reason\": \"Es una RFP válida.\"}\n```"
                )

            mock_client.return_value.chat.completions.create = _fenced
            result = _llm_classify(rfp_formal_vantex)
        assert result is not None
        assert result["is_valid_rfp"] is True


# ═══════════════════════════════════════════════════════════════════════
#  Full classify_rfp node tests (graph-compatible)
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyRfpNode:
    """Tests for the graph node function classify_rfp()."""

    def test_valid_document(self, rfp_formal_vantex):
        state: RFPIntakeState = {"ticket_id": "t-001", "markdown": rfp_formal_vantex}
        result = classify_rfp(state)
        assert result["is_valid_rfp"] is True, f"classify_rfp result: {result}"
        assert "classification_reason" in result
        assert result["classification_reason"]

    def test_invalid_document(self, vendor_pitch_invalid):
        state: RFPIntakeState = {"ticket_id": "t-002", "markdown": vendor_pitch_invalid}
        result = classify_rfp(state)
        assert result["is_valid_rfp"] is False, f"classify_rfp result: {result}"
        assert result["classification_reason"]


# ═══════════════════════════════════════════════════════════════════════
#  Unknown department handling
# ═══════════════════════════════════════════════════════════════════════

class TestUnknownDepartment:
    """What if a RFP mentions a department that doesn't exist in CONTEXT.md?"""

    def test_unknown_service_falls_back_to_seleccion(self):
        """If no known department keyword matches, default to seleccion."""
        from api.services.rfp_intake import _detect_departments
        result = _detect_departments(["Queremos un servicio de contabilidad"])
        assert result == ["seleccion"], (
            f"Unknown service should default to ['seleccion'], got: {result}"
        )

    def test_orchestrator_skips_unknown_department(self, rfp_formal_vantex):
        """The orchestrator only routes to known departments from _DEPARTMENTS."""
        from api.services.rfp_intake import _DEPARTMENTS
        state: RFPIntakeState = {
            "ticket_id": "t-003",
            "markdown": rfp_formal_vantex,
            "is_valid_rfp": True,
            "metadata": {
                "services_requested": ["headhunting", "capacitación"],
                "client_name": "Vantex",
            },
        }
        from api.services.rfp_intake import route_to_departments
        result = route_to_departments(state)
        depts = result.get("departments_needed", [])
        assert all(d in _DEPARTMENTS for d in depts), (
            f"Unknown departments should not be routed: {depts}"
        )