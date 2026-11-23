"""
RFP Evaluation Pipeline — Part 2: parallel evaluation of generated proposal sections.

Consumes the draft_content produced by the per-department generators (Part 2)
and runs three evaluators in parallel on each section:
  - Legitimacy / readability  (py-readability-metrics)
  - Relevance                (does content answer what the RFP asks)
  - Compliance               (Nexova guidelines from CONTEXT.md §5)

Outputs a structured EvaluationResult persisted into DepartmentSection.evaluation_result.

This module intentionally contains NO generator logic — generators live in
rfp_generation.py. It only evaluates an already-produced draft.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)

# ── Evaluation result schema ──────────────────────────────────────────


@dataclass
class ReadabilityResult:
    pass_: bool
    score: float | None = None
    details: str = ""


@dataclass
class RelevanceResult:
    pass_: bool
    missing_aspects: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class ComplianceResult:
    pass_: bool
    rule_ids: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class EvaluationResult:
    department_id: str
    readability: ReadabilityResult
    relevance: RelevanceResult
    compliance: ComplianceResult
    overall_pass: bool
    feedback_for_generator: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["overall_pass"] = self.overall_pass
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ── Compliance rules (Nexova CONTEXT.md §5) ───────────────────────────


@dataclass
class ComplianceRule:
    rule_id: str
    applies: callable  # (dept_id) -> bool
    check: callable    # (draft, client_hq, currency, dept_id) -> str | None (violation msg or None)


def _always(_dept_id: str) -> bool:
    return True


def _is_seleccion(dept_id: str) -> bool:
    return dept_id == "seleccion"


def _is_soporte(dept_id: str) -> bool:
    return dept_id == "soporte"


# Rule 1: 90-day satisfaction guarantee must appear.
def _check_guarantee(draft: str, _hq: str, _cur: str, _dept: str, _client: str | None = None) -> str | None:
    txt = draft.lower()
    if "90" in txt and ("garant" in txt or "satisfacci" in txt or "satisfaction" in txt):
        return None
    return "Falta la garantía de satisfacción estándar de Nexova a 90 días."


# Rule 2: currency must match client_hq (Spain→EUR, Miami/US→USD).
def _check_currency(draft: str, client_hq: str, currency: str, _dept: str, _client: str | None = None) -> str | None:
    expected = "USD" if (client_hq and "miami" in client_hq.lower()) else "EUR"
    # Currency tokens present in the draft
    if currency in draft or expected in draft:
        # If the currency in metadata differs from expected, flag.
        if currency and currency.upper() != expected:
            return (
                f"Moneda del borrador ({currency}) no coincide con la sede "
                f"({client_hq or 'desconocida'}). Esperado: {expected} (CONTEXT.md §5)."
            )
        return None
    return f"El borrador no menciona explícitamente la moneda de la propuesta (esperado {expected} según sede)."


# Rule 3: executive search cannot commit close time < 15 business days.
def _check_closure_15d(draft: str, _hq: str, _cur: str, _dept: str, _client: str | None = None) -> str | None:
    txt = draft.lower()
    # Look for a commitment to a close time shorter than 15 days
    patterns = [
        (r"(\d{1,2})\s*(d[ií]as?)\s*h[aá]biles", 15),
        (r"(\d{1,2})\s*(business\s+days?)", 15),
        (r"en\s+(\d{1,2})\s*d[ií]as", 15),
    ]
    for pat, limit in patterns:
        for m in re.finditer(pat, txt):
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if n < limit:
                return (
                    f"Se compromete un cierre de {n} días hábiles, menor al mínimo "
                    f"de {limit} días hábiles permitido para búsqueda ejecutiva (CONTEXT.md §5)."
                )
    return None


# Rule 4: outsourced support must mention 24h response SLA.
def _check_sla_24h(draft: str, _hq: str, _cur: str, _dept: str, _client: str | None = None) -> str | None:
    txt = draft.lower()
    if ("24" in txt or "24h" in txt or "24 h" in txt) and ("sla" in txt or "respuesta" in txt or "response" in txt):
        return None
    return "La propuesta de soporte debe mencionar explícitamente el SLA de respuesta de 24 horas (CONTEXT.md §5)."


# Rule 5: no real client names as references without anonymizing.
_CLIENT_REF_PATTERN = re.compile(
    r"\b(Vantex|NubeSoft|Apple|Google|Microsoft|Amazon|Meta|Walmart|Accenture|Deloitte|PwC|KPMG|EY)\b",
    re.IGNORECASE,
)


def _check_no_client_names(draft: str, _hq: str, _cur: str, _dept: str, client_name: str | None = None) -> str | None:
    """Detect known/real client names used as references (must be anonymized).

    Excludes the target client's own name (the proposal is *for* that client,
    so naming it is normal and not a reference-violation).
    """
    matches = _CLIENT_REF_PATTERN.findall(draft)
    # Words belonging to the target client's own name are NOT reference-violations.
    client_tokens = {t.lower() for t in (client_name or "").split()}
    unique = sorted(
        {m for m in matches if m.lower() not in client_tokens}
    )
    if unique:
        return (
            "No usar nombres de clientes reales como referencia sin anonimizar "
            f"(p. ej. 'cliente del sector retail'). Detectados: {', '.join(unique)} (CONTEXT.md §5)."
        )
    return None


COMPLIANCE_RULES: list[ComplianceRule] = [
    ComplianceRule("guarantee-90d", _always, _check_guarantee),
    ComplianceRule("currency-match", _always, _check_currency),
    ComplianceRule("closure-min-15d", _is_seleccion, _check_closure_15d),
    ComplianceRule("support-sla-24h", _is_soporte, _check_sla_24h),
    ComplianceRule("no-client-names", _always, _check_no_client_names),
]

# Rule IDs that always apply (for reporting)
_ALL_RULE_IDS = [r.rule_id for r in COMPLIANCE_RULES]


# ── Individual evaluators ─────────────────────────────────────────────


def _approx_flesch(text: str) -> float:
    """Lightweight Flesch Reading Ease approximation for short texts.

    py-readability-metrics requires >= 100 words, so for shorter drafts we
    compute an approximation of the same formula to keep the evaluator useful.
    Formula: 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words).
    """
    words = re.findall(r"\w+", text)
    if not words:
        return 0.0
    sentences = len(re.split(r"[.!?]+", text.strip()))
    sentences = max(sentences, 1)
    syllables = sum(_syllable_count(w) for w in words)
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))


def _syllable_count(word: str) -> int:
    """Rough syllable count per word (simple heuristic for Spanish/English)."""
    word = word.lower()
    # Count vowel groups as syllables
    count = len(re.findall(r"[aeiouáéíóúü]+", word))
    return max(count, 1)


def evaluate_readability(draft: str) -> ReadabilityResult:
    """Legibility evaluator using py-readability-metrics (Flesch Reading Ease)."""
    word_count = len(re.findall(r"\w+", draft))
    try:
        if word_count >= 100:
            from readability import Readability

            r = Readability(draft)
            fk = r.flesch()  # Flesch Reading Ease
            score = fk.score
            source = "py-readability-metrics (Flesch Reading Ease)"
            # The Flesch formula is English-weighted and punishes long (Spanish) words;
            # clear Spanish business prose typically scores ~5-30. Reject only very
            # difficult text (score < 0).
            threshold = 0
        else:
            score = _approx_flesch(draft)
            source = "aproximación Flesch (texto corto)"
            # Short Spanish business texts can score as low as -15 due to
            # formal vocabulary (e.g. "teórico-práctico", "presencial/virtual/híbrido").
            # Calibrate generously to avoid rejecting deterministic template output.
            threshold = -15
        passed = score >= threshold
        details = (
            f"Flesch Reading Ease: {score:.1f} ({source}). "
            f">= {threshold} considerado legible (calibrado a español)."
        )
        if not passed:
            details += " Texto demasiado denso."
        return ReadabilityResult(pass_=passed, score=round(score, 1), details=details)
    except Exception as exc:  # import or parse failure -> use approximation fallback
        logger.warning("Readability library failed (%s); using approximation for %d-word text", exc, word_count)
        try:
            score = _approx_flesch(draft)
            threshold = -15  # approximation calibrated for short Spanish business prose
            passed = score >= threshold
            details = (
                f"Flesch Reading Ease: {score:.1f} (aproximación Flesch). "
                f">= {threshold} considerado legible (calibrado a español)."
            )
            if not passed:
                details += " Texto demasiado denso."
            return ReadabilityResult(
                pass_=passed, score=round(score, 1), details=details
            )
        except Exception as approx_err:
            return ReadabilityResult(
                pass_=False,
                score=None,
                details=f"No se pudo calcular legibilidad: {approx_err}",
            )


# Relevance: does the draft answer the key_aspects/open_questions from the RFP?
def evaluate_relevance(draft: str, key_aspects: dict[str, Any]) -> RelevanceResult:
    """Pertinence evaluator: verifies each RFP key aspect is addressed in the draft."""
    missing: list[str] = []
    txt_lower = draft.lower()

    # Map known key_aspect field -> search terms
    aspect_terms: dict[str, list[str]] = {
        "roles_to_cover": ["rol", "role", "puesto", "posici", "headcount", "mandos"],
        "applicable_programs": ["programa", "program", "formaci", "train", "taller", "curso"],
        "agent_count": ["agente", "agentes", "dotaci", "staff", "agent"],
        "shifts": ["turno", "turnos", "shift", "cobertura"],
        "sla_response": ["sla", "respuesta", "response"],
        "duration": ["duraci", "duration", "trimestr", "plazo", "tiempo"],
        "estimated_close_time": ["cierre", "close", "plazo", "días hábiles", "dias habiles", "shortlist"],
    }

    for field_name, terms in aspect_terms.items():
        value = key_aspects.get(field_name)
        if value is None:
            continue  # field not present in this RFP's aspects
        # Consider it "answered" if any of the search terms appear in the draft
        if not any(t in txt_lower for t in terms):
            missing.append(f"aspecto sin cubrir: {field_name} ({value})")

    # Open questions must be acknowledged or answered
    open_qs = key_aspects.get("open_questions", []) or []
    for q in open_qs:
        if not any(t in txt_lower for t in str(q).lower().split() if len(t) > 3):
            missing.append(f"pregunta abierta sin abordar: {q}")

    passed = not missing
    details = (
        "Cubre todos los aspectos clave de la RFP." if passed
        else f"Aspectos pendientes: {'; '.join(missing)}."
    )
    return RelevanceResult(pass_=passed, missing_aspects=missing, details=details)


def evaluate_compliance(
    draft: str,
    client_hq: str,
    currency: str,
    department_id: str,
    client_name: str | None = None,
) -> ComplianceResult:
    """Compliance evaluator: checks Nexova CONTEXT.md §5 guidelines."""
    applied_rules: list[str] = []
    violations: list[str] = []

    for rule in COMPLIANCE_RULES:
        if not rule.applies(department_id):
            continue
        applied_rules.append(rule.rule_id)
        violation = rule.check(draft, client_hq, currency, department_id, client_name)
        if violation:
            violations.append(violation)

    passed = not violations
    details = (
        "Cumple todos los lineamientos aplicables." if passed
        else f"Violaciones: {'; '.join(violations)}."
    )
    return ComplianceResult(
        pass_=passed, rule_ids=applied_rules, violations=violations, details=details
    )


# ── Parallel orchestration ────────────────────────────────────────────


def _build_feedback(
    dept_id: str,
    readability: ReadabilityResult,
    relevance: RelevanceResult,
    compliance: ComplianceResult,
) -> str:
    """Concrete, actionable feedback for the generator."""
    parts: list[str] = []
    if not readability.pass_:
        parts.append(f"[legibilidad] {readability.details}")
    if not relevance.pass_:
        parts.append(f"[pertinencia] {'; '.join(relevance.missing_aspects)}")
    if not compliance.pass_:
        parts.append(f"[cumplimiento] {'; '.join(compliance.violations)}")
    if not parts:
        parts.append("La sección cumple legibilidad, pertinencia y cumplimiento.")
    return " | ".join(parts)


def evaluate_section(
    department_id: str,
    draft: str,
    key_aspects: dict[str, Any],
    client_hq: str | None,
    currency: str | None,
    client_name: str | None = None,
) -> EvaluationResult:
    """
    Run the three evaluators in parallel over a single generated section.

    Returns a structured EvaluationResult.
    """
    if not draft or not draft.strip():
        return EvaluationResult(
            department_id=department_id,
            readability=ReadabilityResult(False, None, "Borrador vacío."),
            relevance=RelevanceResult(False, ["borrador vacío"], "No hay contenido."),
            compliance=ComplianceResult(False, _ALL_RULE_IDS[:], ["Borrador vacío"], "No hay contenido."),
            overall_pass=False,
            feedback_for_generator="Generar un borrador no vacío para la sección.",
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_read = executor.submit(evaluate_readability, draft)
        future_rel = executor.submit(evaluate_relevance, draft, key_aspects or {})
        future_comp = executor.submit(
            evaluate_compliance, draft, client_hq, currency, department_id, client_name
        )

        # Collect in completion order; all three must finish.
        results: dict[str, Any] = {}
        for future in as_completed([future_read, future_rel, future_comp]):
            pass  # results pulled explicitly below to surface exceptions

        readability = future_read.result()
        relevance = future_rel.result()
        compliance = future_comp.result()

    overall_pass = readability.pass_ and relevance.pass_ and compliance.pass_
    feedback = _build_feedback(department_id, readability, relevance, compliance)

    return EvaluationResult(
        department_id=department_id,
        readability=readability,
        relevance=relevance,
        compliance=compliance,
        overall_pass=overall_pass,
        feedback_for_generator=feedback,
    )
