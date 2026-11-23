"""
Tests for RFP parallel evaluation (Part 2) — no DB required.

Verifies each evaluator (readability, relevance, compliance) and the
parallel orchestration function `evaluate_section` produce a structured
EvaluationResult with the expected fields and pass/fail semantics.
"""
from __future__ import annotations

import json

import pytest

from services.api.services.rfp_evaluation import (
    COMPLIANCE_RULES,
    EvaluationResult,
    evaluate_compliance,
    evaluate_readability,
    evaluate_relevance,
    evaluate_section,
)


# ── Readability evaluator ─────────────────────────────────────────────


class TestReadabilityEvaluator:
    def test_returns_structured_result(self):
        result = evaluate_readability("Texto sencillo y claro. Frases cortas.")
        assert result.pass_ is not None
        assert isinstance(result.pass_, bool)
        assert result.score is None or isinstance(result.score, (int, float))
        assert isinstance(result.details, str)

    def test_readable_text_passes(self):
        # Simple, short-sentence Spanish text should be readable
        result = evaluate_readability(
            "Nexova ofrece servicios de selección. "
            "Cubrimos los roles solicitados. "
            "Entregamos en quince días hábiles. "
            "Garantizamos satisfacción a noventa días. "
            "Nuestro equipo es experto. "
            "Contacte con nosotros hoy."
        )
        assert result.pass_ is True


# ── Relevance evaluator ───────────────────────────────────────────────


class TestRelevanceEvaluator:
    def test_covers_all_aspects_passes(self):
        key_aspects = {
            "roles_to_cover": "5 roles",
            "applicable_programs": "liderazgo",
        }
        draft = (
            "Cubrimos los roles solicitados. "
            "Programa de formación en liderazgo. "
            "Sin preguntas abiertas."
        )
        result = evaluate_relevance(draft, key_aspects)
        assert result.pass_ is True
        assert result.missing_aspects == []

    def test_missing_aspect_is_reported(self):
        key_aspects = {
            "roles_to_cover": "5 roles",
            "applicable_programs": "liderazgo",
        }
        # Draft covers roles but has no mention of programs/training
        draft = "Cubrimos los roles solicitados. Entregamos en 30 días."
        result = evaluate_relevance(draft, key_aspects)
        assert result.pass_ is False
        assert any("programas" in m or "liderazgo" in m for m in result.missing_aspects)

    def test_ignores_fields_not_in_key_aspects(self):
        # A field absent from key_aspects (None) is not required
        key_aspects = {"roles_to_cover": "5 roles"}
        draft = "Cubrimos los roles solicitados."
        result = evaluate_relevance(draft, key_aspects)
        assert result.pass_ is True


# ── Compliance evaluator ──────────────────────────────────────────────


class TestComplianceEvaluator:
    def _compliant_draft(self, dept_id: str = "seleccion") -> str:
        return (
            "Proceso de selección ejecutiva para cubrir 5 roles. "
            "Metodología de headhunting y assessment. "
            "Entregamos el shortlist en 30 días hábiles. "
            "Garantizamos su satisfacción a 90 días. "
            "Precio en EUR. "
            "Referencia: cliente del sector retail."
        )

    def test_compliant_draft_passes(self):
        result = evaluate_compliance(
            self._compliant_draft(), "España", "EUR", "seleccion"
        )
        assert result.pass_ is True
        assert result.violations == []

    def test_guarantee_missing_is_violation(self):
        draft = (
            "Proceso de selección. entregamos en 30 días hábiles. "
            "Precio en EUR. Referencia: cliente del sector retail."
        )
        result = evaluate_compliance(draft, "España", "EUR", "seleccion")
        assert result.pass_ is False
        assert any("garant" in v for v in result.violations)

    def test_currency_mismatch_is_violation(self):
        # Miami HQ -> expected USD, but currency metadata is EUR
        result = evaluate_compliance(
            self._compliant_draft(), "Miami", "EUR", "seleccion"
        )
        assert result.pass_ is False
        assert any("moneda" in v.lower() for v in result.violations)

    def test_closure_under_15_days_is_violation_for_seleccion(self):
        draft = (
            "Proceso de selección. Entregamos en 5 días hábiles. "
            "Garantizamos satisfacción a 90 días. Precio en EUR. "
            "Referencia: cliente del sector retail."
        )
        result = evaluate_compliance(draft, "España", "EUR", "seleccion")
        assert result.pass_ is False
        assert any("15" in v or "días hábiles" in v for v in result.violations)

    def test_closure_rule_does_not_apply_to_capacitacion(self):
        # The 15-day rule only applies to seleccion
        draft = (
            "Programa de formación. Entregamos en 5 días hábiles. "
            "Garantizamos satisfacción a 90 días. Precio en EUR."
        )
        result = evaluate_compliance(draft, "España", "EUR", "capacitacion")
        # No closure-15 violation
        assert not any("15" in v for v in result.violations)

    def test_sla_required_for_soporte(self):
        draft = (
            "12 agentes bilingües. Turnos 24/7. Precio en EUR. "
            "Garantizamos satisfacción a 90 días."
        )
        result = evaluate_compliance(draft, "España", "EUR", "soporte")
        assert result.pass_ is False
        assert any("sla" in v.lower() for v in result.violations)

    def test_sla_not_required_for_seleccion(self):
        draft = self._compliant_draft()
        result = evaluate_compliance(draft, "España", "EUR", "seleccion")
        # No SLA violation for seleccion
        assert not any("sla" in v.lower() for v in result.violations)

    def test_real_client_name_is_violation(self):
        draft = (
            "Garantizamos satisfacción a 90 días. Precio en EUR. "
            "Como referencia, trabajamos con Walmart y Apple."
        )
        result = evaluate_compliance(draft, "España", "EUR", "seleccion")
        assert result.pass_ is False
        assert any("anonim" in v.lower() or "clientes reales" in v.lower() for v in result.violations)

    def test_rule_ids_reported(self):
        result = evaluate_compliance(
            self._compliant_draft(), "España", "EUR", "seleccion"
        )
        assert "guarantee-90d" in result.rule_ids
        assert "currency-match" in result.rule_ids
        assert "closure-min-15d" in result.rule_ids
        assert "no-client-names" in result.rule_ids


# ── Parallel orchestration ────────────────────────────────────────────


class TestEvaluateSection:
    def test_returns_evaluation_result_structure(self):
        draft = (
            "Proceso de selección para 5 roles. "
            "Entregamos en 30 días hábiles. Precio en EUR. "
            "Garantizamos satisfacción a 90 días. "
            "Referencia: cliente del sector retail."
        )
        key_aspects = {"roles_to_cover": "5 roles"}
        result = evaluate_section("seleccion", draft, key_aspects, "España", "EUR")

        assert isinstance(result, EvaluationResult)
        assert result.department_id == "seleccion"
        # Dataclass of results
        assert result.readability.pass_ is not None
        assert result.relevance.pass_ is not None
        assert result.compliance.pass_ is not None
        assert isinstance(result.overall_pass, bool)
        assert isinstance(result.feedback_for_generator, str)

    def test_overall_pass_is_and_of_all(self):
        # Compliant + relevant draft -> pass
        draft = (
            "Proceso de selección para 5 roles. "
            "Cubrimos los roles solicitados. "
            "Entregamos en 30 días hábiles. Precio en EUR. "
            "Garantizamos satisfacción a 90 días. "
            "Referencia: cliente del sector retail."
        )
        result = evaluate_section(
            "seleccion", draft, {"roles_to_cover": "5 roles"}, "España", "EUR"
        )
        assert result.overall_pass is True
        assert "cumple" in result.feedback_for_generator.lower()

    def test_to_json_is_serializable(self):
        draft = (
            "Proceso de selección para 5 roles. "
            "Entregamos en 30 días hábiles. Precio en EUR. "
            "Garantizamos satisfacción a 90 días."
        )
        result = evaluate_section(
            "seleccion", draft, {"roles_to_cover": "5 roles"}, "España", "EUR"
        )
        payload = result.to_json()
        parsed = json.loads(payload)
        assert parsed["department_id"] == "seleccion"
        assert "readability" in parsed
        assert "relevance" in parsed
        assert "compliance" in parsed
        assert "overall_pass" in parsed
        assert "feedback_for_generator" in parsed

    def test_empty_draft_fails(self):
        result = evaluate_section("seleccion", "", {}, "España", "EUR")
        assert result.overall_pass is False


# ── Rule registration sanity ──────────────────────────────────────────


def test_compliance_rules_registered():
    """All 5 CONTEXT.md §5 rules are registered."""
    rule_ids = {r.rule_id for r in COMPLIANCE_RULES}
    assert {"guarantee-90d", "currency-match", "closure-min-15d",
            "support-sla-24h", "no-client-names"} <= rule_ids
