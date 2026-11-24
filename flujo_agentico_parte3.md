# Flujo Agéntico de RFPs: Aprobación y Cierre (Parte 3 de 3)

En la Parte 2 cada departamento ya genera y autoevalúa su sección de la propuesta económica dentro del mismo ticket abierto en la Parte 1. Falta lo más delicado: que un humano de cada departamento dé el visto bueno antes de que el documento final salga hacia el cliente.

Ticket — Aprobación humana y cierre del documento

Contexto: Ya generamos y autoevaluamos cada sección de la propuesta, pero nadie va a firmar una propuesta económica sin que un humano de cada departamento le dé el visto bueno. Esta es la última pieza del flujo que empezamos en la Parte 1 — y tiene que sentirse como una sola experiencia, no como tres proyectos pegados con cinta.

Qué necesito que construyas:

Antes de dar por aprobada la sección de un departamento, el flujo debe pasar por un punto de aprobación humana real — un human-in-the-loop, no solo un evaluador automático más.
El flujo debe detenerse justo antes de esa acción irreversible, guardar el estado con un checkpointer, y poder reanudarse exactamente donde quedó cuando llegue la aprobación — no reiniciar desde cero.
Esa pausa debe afectar solo la rama del departamento que está esperando aprobación; los demás departamentos que ya tengan su sección lista deben poder seguir avanzando en paralelo, no bloquearse entre sí.
Define un límite de iteraciones y un nodo de arbitraje explícito para los desacuerdos entre departamentos. Conéctalo a los triggers de conflicto y al árbitro fijo de tu BRIEFING (reglas o un humano nombrado — no un LLM “votando” entre agentes).
Cuando todos los departamentos den su sign-off, el documento final debe generarse solo, consolidando las secciones aprobadas.
Quiero poder ver, para cualquier ejecución, qué agente hizo qué y en qué orden, porque cuando algo salga mal en producción no vamos a tener tiempo de adivinar.
Cuando termines, corre el flujo completo de principio a fin — desde que se sube la RFP en la Parte 1 hasta que se genera el documento final aquí — y revisa que se sienta como un solo proceso: sin saltos de estado raros, sin mensajes que no coincidan entre partes, sin pasos que se rompan en la transición de una parte a otra.

Acceptance criteria: Una RFP puede recorrer las tres partes de punta a punta, pausarse para aprobación humana por departamento sin bloquear a los demás, y terminar en un documento final generado automáticamente, con trazabilidad completa de cada paso.

— Tu tech lead

📚 Conocimiento complementario: cuándo interrumpir y cuándo poner un guardrail
No todo control debe pausar el flujo para un humano. Los guardrails (validaciones automáticas de esquema, tipo o negocio) deben resolver solos los casos claros; reserva las interrupciones (interrupt) para decisiones que de verdad requieren juicio humano, como aprobar una propuesta económica antes de enviarla a un cliente. Y cuando interrumpas, hazlo de forma acotada: la interrupción debe pausar únicamente la rama del grafo que depende de esa aprobación (la sección de ese departamento y lo que dependa de ella), no el flujo completo — un departamento esperando el visto bueno de su gerente no debería frenar a los demás que ya están listos para avanzar.

Estados del ticket para esta parte (misma fila — nombres del BRIEFING). El ciclo completo está en el BRIEFING; aquí solo necesitas:

Estado	Rol	Cuándo
en_evaluación / needs_human_review	Entrada Parte 2	El ticket llega con borradores + EvaluationResult (incl. secciones al tope)
esperando_aprobación	Parte 3 escribe	Pausa humana mientras alguna aprobación de departamento esté pendiente
terminado	Parte 3 escribe	Documento final guardado y accesible
No inventes estados huérfanos; conserva valores previos de Parte 1/2 en la misma fila cuando no estés en transición.