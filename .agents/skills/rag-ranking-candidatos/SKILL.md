---
name: rag-ranking-candidatos
description: Busca y prioriza candidatos para una vacante usando consulta en lenguaje natural, recuperacion semantica y ranking explicable.
version: 1.0.0
owner: equipo-ai-nexova
---

# Skill: RAG Ranking de Candidatos

## Objetivo unico

Transformar una consulta de reclutamiento en una lista priorizada de candidatos con explicacion breve y accion recomendada para acelerar el primer filtro.

## Cuando usar

- Cuando un recruiter necesita encontrar candidatos desde una descripcion en lenguaje natural.
- Cuando hay que priorizar rapidamente una lista de perfiles para contacto inicial.
- Cuando se requiere justificar por que un candidato esta arriba o abajo del ranking.

## Cuando no usar

- Si el objetivo es solo editar datos de un candidato.
- Si no existe vacante objetivo o criterios minimos definidos.
- Si se necesita una decision final de contratacion (esta skill solo asiste el pre-filtrado).

## Inputs

Todos los inputs son obligatorios salvo que se indique lo contrario.

1. query_natural (string)
- Descripcion libre del perfil buscado.
- Minimo: 20 caracteres.
- Ejemplo: "Ventas B2B SaaS, ingles C1, disponibilidad inmediata en Valencia o remoto".

2. candidate_pool (array<object>)
- Lista de candidatos sobre la que se busca y rankea.
- Minimo: 1 candidato.
- Cada candidato debe incluir:
  - id (string)
  - fullName (string)
  - skills (string[])
  - yearsOfExperience (number)
  - englishLevel (string)
  - availability (string)
  - location (string)
  - expectedSalary (number)
  - seniority (string)

3. ranking_config (object)
- Configuracion de pesos y limites.
- Campos:
  - topN (number, default 10, rango 1..50)
  - weights (object):
    - semantic (0..1)
    - skills (0..1)
    - experience (0..1)
    - english (0..1)
    - availability (0..1)
  - Regla: suma exacta de pesos = 1.0

4. vacancy_constraints (object, opcional)
- Restricciones duras de la vacante.
- Campos opcionales:
  - requiredSkills (string[])
  - minYearsExperience (number)
  - minEnglishLevel (string)
  - maxSalary (number)
  - allowedLocations (string[])
  - remoteAllowed (boolean)

## Output

Objeto con este formato:

- results (array<object>)
  - maximo topN elementos.
  - cada elemento incluye:
    - candidateId (string)
    - fullName (string)
    - score (number, 0..100)
    - scoreBreakdown (object)
      - semantic
      - skills
      - experience
      - english
      - availability
    - explanation (string, 1 a 3 frases)
    - risks (string[])
    - recommendedAction (string, uno de: contact, interview, hold, discard)
- metadata (object)
  - totalCandidatesEvaluated (number)
  - filtersApplied (string[])
  - executionTimeMs (number)
  - skillVersion (string)

## Flujo minimo

1. Parsear query_natural en criterios estructurados.
2. Aplicar filtros duros de vacancy_constraints si existen.
3. Ejecutar recuperacion semantica sobre candidate_pool.
4. Calcular score compuesto con ranking_config.weights.
5. Ordenar descendente por score.
6. Devolver Top N con explicacion y accion recomendada.

## Reglas de negocio

- Nunca devolver candidatos sin id o fullName.
- Si un candidato incumple una restriccion dura, queda excluido antes del ranking.
- Si dos candidatos empatan en score total, desempatar por:
  1) mas requiredSkills cumplidas,
  2) menor distancia salarial a maxSalary,
  3) orden alfabetico por fullName.
- Las explicaciones deben mencionar al menos 2 factores del scoreBreakdown.

## Criterios de aceptacion explicitos y verificables

1. Validacion de contrato de entrada
- Dado un input sin query_natural o con menos de 20 caracteres,
- Cuando se ejecuta la skill,
- Entonces responde error de validacion con codigo INVALID_QUERY.

2. Suma de pesos
- Dado ranking_config.weights cuya suma no es 1.0,
- Cuando se ejecuta la skill,
- Entonces responde error INVALID_WEIGHTS y no genera ranking.

3. Respeto de filtros duros
- Dado vacancy_constraints.requiredSkills con al menos una skill,
- Cuando se ejecuta la skill,
- Entonces 100% de resultados devueltos deben cumplir todas las requiredSkills.

4. Limite Top N
- Dado topN = 5 y pool valido,
- Cuando se ejecuta la skill,
- Entonces results.length <= 5.

5. Rango de score
- Dado cualquier ejecucion valida,
- Cuando se inspecciona results,
- Entonces todo score esta en rango [0, 100].

6. Orden correcto
- Dado cualquier ejecucion valida con 2 o mas resultados,
- Cuando se inspecciona results,
- Entonces el array esta ordenado de mayor a menor score.

7. Explicabilidad minima
- Dado cualquier resultado devuelto,
- Cuando se revisa explanation,
- Entonces menciona al menos 2 factores distintos entre semantic, skills, experience, english y availability.

8. Accion recomendada acotada
- Dado cualquier resultado devuelto,
- Cuando se revisa recommendedAction,
- Entonces su valor pertenece al conjunto: contact, interview, hold, discard.

9. Trazabilidad de ejecucion
- Dado cualquier ejecucion valida,
- Cuando se revisa metadata,
- Entonces incluye totalCandidatesEvaluated, filtersApplied, executionTimeMs y skillVersion.

## Ejemplo breve

Input:
- query_natural: "Busco perfil HR Tech con ingles C1, 5+ años y disponibilidad inmediata"
- topN: 3

Output esperado:
- 3 candidatos maximo, score descendente, explicacion corta por candidato y accion recomendada.
