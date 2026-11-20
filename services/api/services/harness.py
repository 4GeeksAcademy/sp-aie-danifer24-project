"""
Harness de Seguridad para el Agente de Soporte Nexova
=====================================================

Proporciona las capas de proteccion del agente:
1. Guardrails de contenido (pre-generacion): valida la pregunta del usuario
   antes de que entre al grafo.
2. Guardrails de RAG: verifica que los fragmentos recuperados no contengan
   instrucciones enmascaradas como sistema.
3. Guardrails de salida (post-generacion): verifica que la respuesta no
   contenga datos sensibles, instrucciones del sistema, o contenido prohibido.
4. Observabilidad: toda decision de guardrail queda registrada con timestamp.

Cada guardrail es una funcion pura que recibe el texto y devuelve
(HasViolation, Reason, SuggestedAction).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────
#  Observabilidad: contador de activaciones de guardrails
# ────────────────────────────────────────────────────────────────────────

_guardrail_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_stats_lock = Lock()


def _record_guardrail_action(
    guardrail_name: str,
    guardrail_type: str,  # "seguridad", "contenido", "estructural"
    action: str,          # "blocked", "redirected", "passed", "detected"
) -> None:
    """Registra una activacion de guardrail en el contador en memoria."""
    with _stats_lock:
        _guardrail_stats[guardrail_name]["total"] += 1
        _guardrail_stats[guardrail_name][f"type_{guardrail_type}"] += 1
        _guardrail_stats[guardrail_name][action] += 1


def get_guardrail_stats() -> dict[str, Any]:
    """Devuelve un resumen de las activaciones de cada guardrail.

    Returns:
        Dict con:
        - summary: contador por guardrail
        - totals: totales por tipo de fallo
    """
    with _stats_lock:
        stats_snapshot = dict(_guardrail_stats)

    totals: dict[str, int] = defaultdict(int)
    result: dict[str, Any] = {}
    for guardrail_name, counters in sorted(stats_snapshot.items()):
        result[guardrail_name] = dict(counters)
        for key, val in counters.items():
            if key.startswith("type_"):
                totals[key.replace("type_", "")] += val
            elif key in ("blocked", "redirected", "passed"):
                totals[key] += val
            else:
                totals[key] += val

    return {"summary": result, "totals": dict(totals)}


def reset_guardrail_stats() -> None:
    """Resetea los contadores de guardrail (util en tests)."""
    with _stats_lock:
        _guardrail_stats.clear()

# ────────────────────────────────────────────────────────────────────────
#  Tipos
# ────────────────────────────────────────────────────────────────────────

class GuardrailVerdict:
    """Resultado de una comprobacion del guardrail."""
    def __init__(self, passed: bool, reason: str = "", blocked: bool = False):
        self.passed = passed          # True = OK, False = violacion
        self.reason = reason          # Descripcion legible
        self.blocked = blocked        # True = se debe bloquear la respuesta
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_log(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "blocked": self.blocked,
            "timestamp": self.timestamp,
        }

# ────────────────────────────────────────────────────────────────────────
#  PATRONES DE DETECCION
# ────────────────────────────────────────────────────────────────────────

# Intentos de jailbreak / cambio de instrucciones (pre-grafo)
_JAILBREAK_PATTERNS = [
    r"ignora\s+(?:tus\s+)?instrucciones(?:\s+(?:anteriores|previas))?",
    r"olvida\s+(?:que\s+)?(?:trabajas|eres|tu\s+rol)",
    r"ahora\s+eres?\s+un\s+asistente\s+sin\s+reglas",
    r"act[uú]a\s+como\s+si\s+no\s+(?:tuvieras|hubiera)",
    r"nuevas?\s+instrucciones?\s+del\s+sistema",
    r"ree scrapete\s+(?:tus\s+)?reglas",
    r"bypass\s+(?:de\s+)?seguridad",
    r"System\s*(?:Prompt|Message|Instruction)",
    r"\[SYSTEM\]",
    r"eres?\s+un\s+(?:agente|asistente)\s+(?:libre|sin\s+restricciones)",
    r"no\s+tienes?\s+(?:reglas|l[ií]mites|restricciones)",
    r"haz\s+lo\s+que\s+(?:te\s+)?pida\s+sin\s+preguntar",
]

# Reformulaciones explicitas de cambio de instrucciones (tres enfoques distintos)
# Reformulacion 1: Instruccion directa "reescribe/ignora/comportate como si..."
# Reformulacion 2: Peticion encubierta "que pasaria si... / imagina que eres..."
# Reformulacion 3: Afirmacion de que el system prompt original ya no aplica
_JAILBREAK_REFORMULATIONS = [
    # Reformulacion 1: Orden directa disfrazada de nueva instruccion del sistema
    [
        r"reescrib(?:e|as)\s+tus\s+(?:reglas|instrucciones|pautas)\s+(?:para|y\s+)",
        r"nuevas?\s+directrices?\s+(?:del\s+)?sistema",
        r"actualiza\s+tu\s+(?:prompt|instrucciones|configuraci[oó]n)",
        r"cambia\s+tu\s+(?:comportamiento|personalidad|rol)",
        r"modifica\s+tus?\s+(?:reglas?|l[ií]mites|restricciones)",
    ],
    # Reformulacion 2: Escenario hipotetico para eludir restricciones
    [
        r"imagin[aá]?\s+que\s+eres?\s+(?:un\s+)?(?:nuev[oa]?\s+)?asistente(?:\s|\.|,|$)",
        r"simulemos?\s+que\s+no\s+(?:tienes|hay)",
        r"que\s+pasaria\s+si\s+",
        r"finge\s+que\s+",
        r"sup[oó]n\s+que\s+",
    ],
    # Reformulacion 3: Afirmar que las restricciones originales ya no aplican
    [
        r"tus?\s+(?:reglas|restricciones?|l[ií]mites)\s+(?:ya\s+)?no\s+(?:aplican|son\s+v[aá]lidas|existen)",
        r"las?\s+instrucciones?\s+anteriores?\s+(?:ya\s+)?no\s+(?:son\s+)?v[aá]lidas?",
        r"el\s+(?:acuerdo|contrato|convenio)\s+ha\s+cambiado",
        r"las?\s+condiciones?\s+han\s+cambiado",
        r"el\s+sistema\s+(?:se\s+)?ha\s+(?:actualizado|cambiado|reiniciado)",
    ],
]

# Solicitudes de uso como chatbot personal (pre-grafo)
_CHATBOT_PERSONAL_PATTERNS = [
    r"escr[ií]b(?:e|eme)\s+un\s+(ensayo|poema|cuento|art[ií]culo|informe|reporte)",
    r"ay[uú]dame\s+a?\s+(?:hacer|escribir|crear|preparar)\s+(?:mi\s+)?(?:tarea|deberes|trabajo|ensayo|tesis|cv|curriculum|curr[ií]culum)",
    r"genera?\s*(?:me\s+)?c[oó]digo\s+(?:para|de)\s+(?!.*(?:nexova|soporte|incidencia|api|conexi[oó]n))",
    r"haz\s+(?:de\s+|una\s+|como\s+(?:si\s+)?(?:fueras\s+)?(?:mi\s+|un\s+)?)?(?:tarea|terapeuta|psic[oó]logo|coach|profesor|tutor|abogado|m[eé]dico)",
    r"eres?\s+mi\s+(?:asistente\s+)?personal",
    r"convi[eé]rtete\s+en\s+mi\s+",
    r"que\s+opinas?\s+de\s+(?:mi\s+)?(?:vida|relaci[oó]n|situaci[oó]n\s+personal|decisi[oó]n)",
    r"traduce\s+(?:esto|al\s+...|siguiente)",
    r"resume\s+(?:este\s+)?(?:art[ií]culo|texto|libro|documento|video|noticia)",
    r"dame\s+un\s+consejo\s+(?:sobre|para|acerca\s+de)",
    r"necesito\s+que\s+me\s+ayudes?\s+con\s+(?!.*(?:ticket|incidencia|soporte))",
    r"hazme\s+un\s+(?:resumen|an[aá]lisis|esquema|plan)",
    r"act[uú]a\s+como\s+mi\s+",
    r"quiero\s+que\s+seas?\s+mi\s+",
    r"corrige\s+(?:mi\s+)?(?:texto|redacci[oó]n|gram[aá]tica|ingl[eé]s)",
    r"escr[ií]b(?:e|eme)\s+un\s+email|correo\s+(?!.*(?:ticket|soporte|incidencia))",
    r"juega\s+(?:conmigo|a\s+)",
    r"cu[eé]ntame\s+un\s+(?:chiste|cuento|historia)",
]

# Intento de cruce entre cuentas de cliente (pre-grafo)
_CROSS_CLIENT_PATTERNS = [
    r"otr[oa]\s+(?:cliente|empresa|cuenta)",
    r"diferente\s+(?:cliente|cuenta|empresa)",
    r"SLA\s+de\s+otr[oa]",
    r"tarifas?\s+de\s+otr[oa]",
    r"contrato\s+de\s+otr[oa]",
]

# Datos sensibles en respuestas (post-generacion) — coincide con CONTEXT.md seccion 3
_SENSITIVE_DATA_PATTERNS = [
    r"\b(?:contrase[ñn]a|password|token|api[_\s]*key|secret)\s*[:=]\s*\S+",
    r"\bcontrase[ñn]a\s+(?:es|del|de\s+la|:)\s+\S+",
    r"\b(?:Bearer|JWT|Basic)\s+\S{8,}",
    r"(?:tarifas?|precios?|costes?)\s*(?:del\s+)?contrato\s+",
    r"SLA\s+(?:penalizado|penalizaci[óo]n|m[uú]lt[aá])",
    r"t[eé]rminos?\s+comerciales?\s+del\s+contrato",
    r"condiciones?\s+contractuales?\s+de\s+nexova",
    r"\bAKA_",
    r"\bnexova[_\s]?(?:mcp|token|secret|key|bearer)",
    r"\bapi[_\s]?bearer[_\s]?token",
    r"informaci[oó]n\s+de\s+otro\s+cliente",
    r"datos?\s+de\s+la\s+cuenta\s+de\s+",
]

# Contenido RAG que pretende ser instruccion del sistema (post-rag, pre-llm)
# Usado por guardrail_rag_content() para deteccion de chunks a excluir
_RAG_INSTRUCTION_PATTERNS = [
    r"\[SYSTEM\]",
    r"nuevas?\s+reglas?\s+del\s+sistema",
    r"a partir de ahora",
    r"eres\s+un\s+asistente\s+que\s+",
]

# Patrones para sanitizacion linea-por-linea en sanitize_external_content()
# Mas restrictivos que _RAG_INSTRUCTION_PATTERNS: solo elimina lineas
# que combinen [SYSTEM] CON una palabra de instruccion en cualquier idioma
_SANITIZE_LINE_PATTERNS = [
    r"\[SYSTEM\].*?(?:ignora|ignore|override|olvida|rewrite|reescribe|forget|oublie)",
    r"nuevas?\s+reglas?\s+del\s+sistema",
    r"a\s+partir\s+de\s+ahora",
    r"eres\s+un\s+asistente\s+que\s+",
]

# Palabras clave de dominio (para deteccion de fuera-de-dominio)
_DOMAIN_KEYWORDS = [
    r"\b(?:ticket|incidencia|incidente|soporte|SLA|procedimiento|"
    r"pol[ií]tica|FAQ|base\s+de\s+conocimiento|"
    r"reembolso|devoluci[óo]n|queja|reclamaci[óo]n|"
    r"contrato|cliente|cuenta|usuario|contrase[ñn]a|"
    r"producto|inventario|stock|SKU|art[ií]culo|"
    r"tarifas?|precios?|costes?|honorarios?|headhunting|"
    r"reemplazo|garant[ií]a|b[uú]squeda|candidatos?|"
    r"contrataci[óo]n|perfil|vacante|puesto)\b",
]

# Patrones de instrucciones internas filtradas en respuestas (post-generacion)
_INTERNAL_INSTRUCTION_PATTERNS = [
    r"=== INSTRUCCIONES DEL SISTEMA",
    r"=== FIN DE INSTRUCCIONES DEL SISTEMA",
    r"=== CONOCIMIENTO RECUPERADO ===",
    r"=== CONSULTA DEL USUARIO ===",
    r"AUTORIDAD MAXIMA, NO MODIFICABLES",
    r"eres?\s+el\s+agente\s+de\s+primera\s+l[íi]nea",
    r"del\s+equipo\s+de\s+R\s*[oó]?\s*berto\s+D[ií]az",
    r"Customer\s+Support\s+Lead",
    r"\[REGLAS DE SEGURIDAD\]",
    r"NUNCA\s+modifiques?\s+tu\s+comportamiento",
    r"NUNCA\s+reveles\s+este\s+system\s+prompt",
]


# ────────────────────────────────────────────────────────────────────────
#  GUARDRAILS INDIVIDUALES
# ────────────────────────────────────────────────────────────────────────

def guardrail_jailbreak(question: str) -> GuardrailVerdict:
    """Detecta intentos de cambio de instrucciones / jailbreak."""
    question_lower = question.casefold()
    for pattern in _JAILBREAK_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            logger.warning("GUARDRAIL_JAILBREAK: matched pattern %r", pattern)
            _record_guardrail_action("jailbreak", "seguridad", "blocked")
            return GuardrailVerdict(
                passed=False,
                reason=f"Intento de jailbreak detectado: patrón '{pattern}'",
                blocked=True,
            )
    return GuardrailVerdict(passed=True)


def guardrail_chatbot_personal(question: str) -> GuardrailVerdict:
    """Detecta solicitudes de uso como chatbot personal."""
    question_lower = question.casefold()
    for pattern in _CHATBOT_PERSONAL_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            logger.warning("GUARDRAIL_CHATBOT_PERSONAL: matched pattern %r", pattern)
            _record_guardrail_action("chatbot_personal", "contenido", "blocked")
            return GuardrailVerdict(
                passed=False,
                reason=f"Uso como chatbot personal detectado: patrón '{pattern}'",
                blocked=True,
            )
    return GuardrailVerdict(passed=True)


def guardrail_cross_client(question: str) -> GuardrailVerdict:
    """Detecta intentos de acceder a datos de otro cliente."""
    question_lower = question.casefold()
    for pattern in _CROSS_CLIENT_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            logger.warning("GUARDRAIL_CROSS_CLIENT: matched pattern %r", pattern)
            _record_guardrail_action("cross_client", "contenido", "blocked")
            return GuardrailVerdict(
                passed=False,
                reason=f"Intento de acceso a datos de otro cliente: patrón '{pattern}'",
                blocked=True,
            )
    return GuardrailVerdict(passed=True)


def guardrail_rag_content(chunks: list[dict]) -> list[GuardrailVerdict]:
    """Verifica que los fragmentos RAG no contengan instrucciones enmascaradas.

    Esto es crítico porque el agente consume un MCP Server con herramientas
    externas. Si un documento recuperado contiene "ignora tus reglas", el
    modelo no debe tratarlo como instrucción.

    Devuelve un veredicto POR CHUNK (mismo orden que chunks).
    """
    results = []
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        if not text:
            results.append(GuardrailVerdict(passed=True))
            continue
        text_lower = text.casefold()
        matched = False
        for pattern in _RAG_INSTRUCTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(
                    "GUARDRAIL_RAG_INSTRUCTION: chunk[%d] matched pattern %r",
                    i, pattern,
                )
                matched = True
                _record_guardrail_action("rag_content", "seguridad", "detected")
                results.append(GuardrailVerdict(
                    passed=False,
                    reason=(
                        f"El fragmento RAG [{i}] contiene texto que podría "
                        f"interpretarse como instrucción del sistema. "
                        f"Se marca para exclusion del contexto: patrón '{pattern}'"
                    ),
                    blocked=False,  # No bloqueamos toda la respuesta, solo ese chunk
                ))
                break
        if not matched:
            results.append(GuardrailVerdict(passed=True))
    return results


def guardrail_sensitive_output(answer: str) -> GuardrailVerdict:
    """Verifica que la respuesta generada no contenga datos sensibles."""
    answer_lower = answer.casefold()
    for pattern in _SENSITIVE_DATA_PATTERNS:
        if re.search(pattern, answer_lower, re.IGNORECASE):
            logger.warning("GUARDRAIL_SENSITIVE_OUTPUT: matched pattern %r", pattern)
            _record_guardrail_action("sensitive_output", "seguridad", "blocked")
            return GuardrailVerdict(
                passed=False,
                reason=f"Posible fuga de datos sensibles en la respuesta: patrón '{pattern}'",
                blocked=True,
            )
    return GuardrailVerdict(passed=True)


def guardrail_domain_check(question: str) -> GuardrailVerdict:
    """Clasifica si la pregunta esta dentro del dominio de soporte.

    No bloquea, solo informa para trazabilidad.
    """
    question_lower = question.casefold()
    has_domain_keyword = bool(re.search("|".join(_DOMAIN_KEYWORDS), question_lower, re.IGNORECASE))

    if not has_domain_keyword and len(question.split()) > 3:
        # Podria ser fuera de dominio, pero no bloqueamos - el system prompt
        # ya maneja la redireccion.
        _record_guardrail_action("domain_check", "contenido", "detected")
        return GuardrailVerdict(
            passed=True,
            reason="Consulta fuera de dominio - se informa para trazabilidad",
            blocked=False,
        )
    return GuardrailVerdict(passed=True)


def guardrail_redirect_smalltalk(question: str) -> GuardrailVerdict:
    """Detecta small talk para enriquecer la observabilidad.

    No bloquea, solo registra.
    """
    smalltalk = re.search(
        r"\b(?:hola|buenos?\s+d[ií]as|buenas\s+tardes|"
        r"c[oó]mo\s+est[aá]s|qu[eé]\s+tal|gracias|adios|chao|"
        r"buenas\s+noches|nos\s+vemos|hasta\s+luego|cuidate)\b",
        question, re.IGNORECASE,
    )
    if smalltalk and len(question.split()) <= 6:
        logger.info("GUARDRAIL_SMALLTALK: small talk detectado, se aplicara redireccion")
        _record_guardrail_action("redirect_smalltalk", "estructural", "redirected")
        return GuardrailVerdict(
            passed=True,
            reason="Small talk detectado - el system prompt redirige al proposito de soporte",
            blocked=False,
        )
    return GuardrailVerdict(passed=True)


def guardrail_output_format(answer: str) -> GuardrailVerdict:
    """Valida que la respuesta generada tenga el formato esperado.

    Comprueba:
    - Longitud minima de respuesta.
    - No termine de forma abrupta (corte en medio de frase).
    - Contenido no vacio despues de limpiar whitespace.
    """
    stripped = answer.strip()
    if not stripped:
        return GuardrailVerdict(
            passed=False,
            reason="Respuesta vacia o solo whitespace",
            blocked=True,
        )
    if len(stripped) < 5:
        return GuardrailVerdict(
            passed=False,
            reason="Respuesta demasiado corta (menos de 5 caracteres)",
            blocked=True,
        )
    # Detectar corte abrupto (ultimos 3 caracteres no son puntuacion ni cierre normal)
    last_char = stripped[-1]
    abrupt_endings = re.search(r"[a-záéíóúñ,;:](?:\s*)$", stripped[-10:], re.IGNORECASE)
    if abrupt_endings and len(stripped) > 20:
        # Solo warning, no bloquear - podria ser respuesta valida corta
        logger.info("GUARDRAIL_FORMAT: posible respuesta con corte abrupto (ultimo char: %r)", last_char)
        _record_guardrail_action("output_format", "estructural", "detected")
    return GuardrailVerdict(passed=True)


def guardrail_internal_instructions(answer: str) -> GuardrailVerdict:
    """Detecta si la respuesta contiene fragmentos del system prompt o
    instrucciones internas que nunca deberian filtrarse."""
    answer_lower = answer.casefold()
    for pattern in _INTERNAL_INSTRUCTION_PATTERNS:
        if re.search(pattern, answer_lower, re.IGNORECASE):
            logger.warning(
                "GUARDRAIL_INTERNAL_LEAK: respuesta contiene instruccion interna filtrada: patron %r",
                pattern,
            )
            _record_guardrail_action("internal_instructions", "seguridad", "blocked")
            return GuardrailVerdict(
                passed=False,
                reason=f"Instruccion interna filtrada en respuesta: patrón '{pattern}'",
                blocked=True,
            )
    return GuardrailVerdict(passed=True)


def guardrail_jailbreak_reformulations(question: str) -> GuardrailVerdict:
    """Detecta intentos de cambio de instrucciones en tres familias de reformulacion.

    Reformulacion 1: Orden directa disfrazada de nueva instruccion del sistema
      ("reescribe tus reglas para...", "nuevas directrices del sistema")
    Reformulacion 2: Escenario hipotetico para eludir restricciones
      ("imagina que eres un nuevo asistente...", "que pasaria si...")
    Reformulacion 3: Afirmacion de que las restricciones originales ya no aplican
      ("tus reglas ya no son validas", "el sistema se ha actualizado")

    Cada reformulacion se evalua independientemente. Basta con que UNA de las
    tres familias coincida para bloquear — no es necesario que las tres coincidan.
    """
    q_lower = question.casefold()
    for family_idx, family in enumerate(_JAILBREAK_REFORMULATIONS, 1):
        for pattern in family:
            if re.search(pattern, q_lower, re.IGNORECASE):
                logger.warning(
                    "GUARDRAIL_JAILBREAK_REFORMULATION: familia %d matched %r",
                    family_idx, pattern,
                )
                _record_guardrail_action("jailbreak_reformulations", "seguridad", "blocked")
                return GuardrailVerdict(
                    passed=False,
                    reason=(
                        f"Intento de cambio de instrucciones detectado "
                        f"(reformulacion tipo {family_idx}): patrón '{pattern}'"
                    ),
                    blocked=True,
                )
    return GuardrailVerdict(passed=True)


def sanitize_external_content(text: str, source_label: str = "external") -> str:
    """Sanitiza contenido proveniente de tools externas o RAG.

    El contenido externo NUNCA debe tratarse como instruccion del sistema.
    Esta funcion:
    1. Extrae y descarta cualquier fragmento que coincida con patrones de
       instruccion enmascarada.
    2. Neutraliza cualquier marcador [SYSTEM] o similar quitandole la
       apariencia de autoridad.
    3. Opcionalmente wrappea el contenido en un bloque declarativo.

    Args:
        text: Texto proveniente de tool externa o chunk RAG.
        source_label: Etiqueta de origen para el log.

    Returns:
        Texto sanitizado, con fragmentos peligrosos eliminados o neutralizados.
    """
    if not text:
        return text

    original = text

    # 1. Eliminar fragmentos con patrones de instruccion enmascarada
    #    Usa _SANITIZE_LINE_PATTERNS (mas restrictivo) para no eliminar
    #    menciones inocuas como "el marcador [SYSTEM]" sin contexto peligroso
    cleaned_lines = []
    for line in text.splitlines():
        skip = False
        for pattern in _SANITIZE_LINE_PATTERNS:
            if re.search(pattern, line.casefold(), re.IGNORECASE):
                logger.info(
                    "SANITIZE_REMOVE [%s]: linea omitida por patrón %r: %.80s",
                    source_label, pattern, line,
                )
                skip = True
                break
        if not skip:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 2. Neutralizar cualquier marcador [SYSTEM] o [INSTRUCTION] que haya
    #    quedado despues del paso 1
    text = re.sub(
        r'\[(SYSTEM|INSTRUCTION|SYS|INST|PROMPT|MODE|GUARDRAIL)\]',
        r'[\1_NEUTRALIZED]',
        text,
        flags=re.IGNORECASE,
    )

    # 3. Si el contenido se redujo a vacio, registrar
    if text.strip() and not text.strip() == original.strip():
        logger.info(
            "SANITIZE_MODIFIED [%s]: contenido modificado (%d chars eliminados)",
            source_label, len(original) - len(text),
        )
    elif not text.strip():
        logger.info(
            "SANITIZE_EMPTIED [%s]: todo el contenido fue eliminado por sanitizacion",
            source_label,
        )

    return text


# ────────────────────────────────────────────────────────────────────────
#  COMPUESTOS: PRE-FLIGHT Y POST-FLIGHT
# ────────────────────────────────────────────────────────────────────────

def pre_graph_guardrails(question: str) -> dict:
    """Ejecuta todos los guardrails pre-grafo sobre la pregunta del usuario.

    Returns:
        Dict con:
        - blocked (bool): True si se debe rechazar la consulta
        - block_reason (str): Explicacion del bloqueo
        - verdicts (list): Todos los veredictos individuales
        - redirected (bool): True si se recomienda redireccion
    """
    verdicts = [
        guardrail_jailbreak(question),
            guardrail_jailbreak_reformulations(question),
        guardrail_chatbot_personal(question),
        guardrail_cross_client(question),
        guardrail_domain_check(question),
        guardrail_redirect_smalltalk(question),
    ]

    blocked_verdicts = [v for v in verdicts if v.blocked]
    blocked = len(blocked_verdicts) > 0
    block_reason = blocked_verdicts[0].reason if blocked_verdicts else ""
    needs_redirect = any(
            "redireccion" in v.reason or "redirige" in v.reason for v in verdicts
    )

    return {
        "blocked": blocked,
        "block_reason": block_reason,
        "verdicts": [v.to_log() for v in verdicts],
        "redirected": needs_redirect,
    }


def post_rag_guardrails(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Filtra y sanitiza fragmentos RAG que contengan instrucciones enmascaradas.

    Aplica dos fases de proteccion:
    Fase 1 — Deteccion: identifica chunks con patrones de instruccion enmascarada
    y los elimina del contexto que vera el LLM (verdict block=False = exclusion).
    Fase 2 — Sanitizacion: sobre los chunks restantes, aplica sanitize_external_content()
    para neutralizar cualquier marcador residual.

    Returns:
        Tuple (safe_chunks, verdict_logs).
    """
    # Fase 1: detectar y excluir chunks con instrucciones enmascaradas
    verdicts = guardrail_rag_content(chunks)
    blocked_indices = set()
    for i, v in enumerate(verdicts):
        if not v.passed:
            blocked_indices.add(i)

    safe_chunks = [
        chunk for i, chunk in enumerate(chunks)
        if i not in blocked_indices
    ]

    removed = len(chunks) - len(safe_chunks)
    if removed > 0:
        logger.info(
            "GUARDRAIL_RAG_FILTER: removed %d/%d chunks with masked instructions",
            removed, len(chunks),
        )

    # Fase 2: sanitizar los chunks restantes (neutralizar [SYSTEM] residual, wrappear)
    sanitized_chunks = []
    for chunk in safe_chunks:
        sanitized = dict(chunk)
        source = chunk.get("source_document", "rag_chunk")
        sanitized["text"] = sanitize_external_content(chunk.get("text", ""), source_label=source)
        sanitized["sanitized"] = sanitized["text"] != chunk.get("text", "")
        sanitized_chunks.append(sanitized)

    contar_sanitizados = sum(1 for c in sanitized_chunks if c.get("sanitized"))
    if contar_sanitizados > 0:
        logger.info(
            "SANITIZE_POST_RAG: %d/%d chunks sanitizados",
            contar_sanitizados, len(sanitized_chunks),
        )

    return sanitized_chunks, [v.to_log() for v in verdicts]


def post_generation_guardrails(answer: str, question: str = "") -> dict:
    """Verifica la respuesta generada antes de enviarla al usuario.

    Incluye:
    - Deteccion de datos sensibles en la respuesta.
    - Deteccion de instrucciones internas filtradas.
    - Validacion de formato basico.
    - Si la pregunta original fue small talk, anade redireccion al final.

    Args:
        answer: Respuesta generada por el LLM.
        question: Pregunta original del usuario (para detectar small talk).

    Returns:
        Dict con:
        - blocked (bool): True si se debe censurar la respuesta
        - block_reason (str): Explicacion del bloqueo
        - safe_answer (str): Respuesta segura (original o censurada, con redireccion si aplica)
        - verdicts (list): Veredictos individuales
    """
    verdicts = [
        guardrail_sensitive_output(answer),
        guardrail_internal_instructions(answer),
        guardrail_output_format(answer),
    ]

    blocked_verdicts = [v for v in verdicts if v.blocked]
    blocked = len(blocked_verdicts) > 0
    block_reason = blocked_verdicts[0].reason if blocked_verdicts else ""

    if blocked:
        safe_answer = (
            "Lo siento, no puedo proporcionar esa información. "
            "Si tienes alguna otra consulta sobre tu ticket de soporte, estaré encantado de ayudarte."
        )
    else:
        safe_answer = answer

    # ── Si la pregunta original era small talk, anadir redireccion al final ──
    was_smalltalk = False
    if question:
        st_verdict = guardrail_redirect_smalltalk(question)
        was_smalltalk = st_verdict.passed and "redirige" in st_verdict.reason
        verdicts.append(st_verdict)

    if was_smalltalk and not blocked:
        # Anadir redireccion si no esta ya presente
        redirect_phrase = "Por cierto, ¿en qué puedo ayudarte con tu ticket de soporte hoy?"
        if redirect_phrase not in safe_answer:
            safe_answer = safe_answer.rstrip() + f"\n\n{redirect_phrase}"

    return {
        "blocked": blocked,
        "block_reason": block_reason,
        "safe_answer": safe_answer,
        "was_redirected": was_smalltalk and not blocked,
        "verdicts": [v.to_log() for v in verdicts],
    }