"""
Intention classifier for memory proposals.

Evaluates whether the user's message approves, rejects, edits,
or is ambiguous about the pending proposal.

Rules are **explicit** (regex-based) to avoid false positives
from natural-language politeness (e.g. "sí" in "sí, pero…").
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class MemoryVerdict(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    AMBIGUOUS = "ambiguous"


class MemoryClassifier:
    """
    Classifies the user's response with respect to a pending memory proposal.

    Usage::

        verdict, edited_content = MemoryClassifier.classify(msg, proposal)
    """

    # ── Approval patterns ──────────────────────────────────────────────────
    # Must be unambiguous standalone confirmations.
    _APPROVED_PATTERNS: list[tuple[re.Pattern, str]] = [
        # "sí", "si", "ok", "okay", "vale", "de acuerdo", "adelante",
        # "guárdalo", "guardalo", "recuérdalo", "recuerdalo",
        # "sí, guárdalo", "sí, recuérdalo"
        (re.compile(r"^\s*(?:s[ií]|ok(?:ay)?|vale|de acuerdo|adelante)\s*[.!]?\s*$", re.IGNORECASE), "simple_yes"),
        (re.compile(r"^\s*(?:s[ií])[\s,]+(?:gu[aá]rdalo|recu[eé]rdalo|guarda|recuerda)\s*[.!]?\s*$", re.IGNORECASE), "yes_store"),
        (re.compile(r"^\s*gu[aá]rdalo\s*[.!]?\s*$", re.IGNORECASE), "store_it"),
        (re.compile(r"^\s*recu[eé]rdalo\s*[.!]?\s*$", re.IGNORECASE), "remember_it"),
        # "guarda eso", "recuerda eso", "guarda esa información"
        (re.compile(r"^\s*guarda\s+(?:eso|esta?\s+informaci[oó]n|lo)\s*[.!]?\s*$", re.IGNORECASE), "store_that"),
        (re.compile(r"^\s*recuerda\s+(?:eso|esta?\s+informaci[oó]n|lo)\s*[.!]?\s*$", re.IGNORECASE), "remember_that"),
        # Affirmative single-word: "sip", "sipo", "simón"
        (re.compile(r"^\s*(?:sip|sipo|sim[oó]n|claro|seguro|confirmo|correcto|exacto)\s*[.!]?\s*$", re.IGNORECASE), "affirmative"),
    ]

    # ── Rejection patterns ─────────────────────────────────────────────────
    _REJECTED_PATTERNS: list[tuple[re.Pattern, str]] = [
        # "no", "no guardes", "no recuerdes"
        (re.compile(r"^\s*no\s*[.!]?\s*$", re.IGNORECASE), "simple_no"),
        (re.compile(r"^\s*no\s+(?:gu[aá]rdes|recuerdes|lo\s+gu[aá]rdes|lo\s+recuerdes)\s*[.!]?\s*$", re.IGNORECASE), "no_store"),
        (re.compile(r"^\s*(?:no\s+gracias|no,\s*gracias|gracias\s*,\s*no)\s*[.!]?\s*$", re.IGNORECASE), "no_thanks"),
        # "quita eso", "descarta", "olvídalo", "no importa"
        (re.compile(r"^\s*(?:quita|descarta|olv[ií]dalo|no\s+importa|d[eé]jalo|d[eé]jalo\s+estar)\s*[.!]?\s*$", re.IGNORECASE), "dismiss"),
        # "no hace falta", "no es necesario"
        (re.compile(r"^\s*no\s+(?:hace\s+falta|es\s+necesario)\s*[.!]?\s*$", re.IGNORECASE), "not_needed"),
        # "fue cosa de una vez", "fue puntual"
        (re.compile(r"^\s*(?:fue\s+(?:cosa\s+de\s+una\s+vez|puntual|algo\s+puntual|s[oó]lo\s+esta\s+vez))\s*[.!]?\s*$", re.IGNORECASE), "one_off"),
    ]

    # ── Edit patterns ──────────────────────────────────────────────────────
    # User corrects the proposed fact; we extract the corrected content.
    _EDITED_PATTERNS: list[tuple[re.Pattern, str]] = [
        # "en realidad era...", "corrige a...", "mejor dicho..."
        (re.compile(r"^\s*(?:en\s+realidad\s+era|corrige\s+(?:a|esto)|mejor\s+dicho|realmente\s+es|la\s+versi[oó]n\s+correcta\s+es)\s*[:\s]+(.+?)\s*[.!]?\s*$", re.IGNORECASE), "correction"),
        # "no, era [contenido]" — rejected content part but provides correct version
        (re.compile(r"^\s*no[\s,]+(?:era|es|ser[ií]a)\s+(.+?)\s*[.!]?\s*$", re.IGNORECASE), "no_was"),
        # Edits with "en lugar de X, Y"
        (re.compile(r"^\s*(?:en\s+lugar\s+de\s+)?(.+?)\s*(?:en\s+realidad|corrige\s+por)\s+(.+?)\s*[.!]?\s*$", re.IGNORECASE), "replace_with"),
    ]

    @classmethod
    def classify(cls, message: str, proposal: Optional[dict] = None) -> tuple[MemoryVerdict, Optional[str]]:
        """
        Classify the user's *message* against a pending *proposal*.

        Returns ``(MemoryVerdict, edited_content)`` where *edited_content* is
        only populated when the verdict is ``EDITED``.

        Priority order: EDITED > REJECTED > APPROVED > AMBIGUOUS
        """
        if not message or not message.strip():
            return MemoryVerdict.AMBIGUOUS, None

        msg_stripped = message.strip()

        # 1. Check for edits first (explicit correction patterns)
        for pattern, label in cls._EDITED_PATTERNS:
            match = pattern.match(msg_stripped)
            if match:
                groups = match.groups()
                # Take the last non-None group as the corrected content
                edited = next((g for g in reversed(groups) if g), None)
                if edited:
                    return MemoryVerdict.EDITED, edited.strip()

        # 2. Check rejection patterns
        for pattern, label in cls._REJECTED_PATTERNS:
            if pattern.match(msg_stripped):
                return MemoryVerdict.REJECTED, None

        # 3. Check approval patterns
        for pattern, label in cls._APPROVED_PATTERNS:
            if pattern.match(msg_stripped):
                return MemoryVerdict.APPROVED, None

        # 4. If the user explicitly mentions the proposal content,
        #    treat as approved (e.g. "sí, los tickets urgentes van a senior")
        if proposal:
            proposal_content = (proposal.get("fact") or proposal).get("content", "")
            if proposal_content and proposal_content.casefold() in msg_stripped.casefold():
                # Contains the exact proposal — likely affirming
                if re.search(r"\b(s[ií]|ok|vale|correcto|exacto)\b", msg_stripped, re.IGNORECASE):
                    return MemoryVerdict.APPROVED, None

        # 5. Ambiguous — never assume approval from silence or topic change
        return MemoryVerdict.AMBIGUOUS, None