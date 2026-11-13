# Diseño de la solución RAG de Nexova

## Propósito y alcance

El asistente permite que los SDRs y account managers consulten en lenguaje natural el conocimiento comercial de Nexova. Recupera evidencia de los documentos de `docs/company-knowledge-base/` y genera una respuesta en español desde la perspectiva de un vendedor de Nexova. No debe presentar resultados crudos de Qdrant ni completar con conocimiento externo las condiciones que no aparezcan en los documentos.

La solución usa el SDK de Qdrant y el cliente compatible con OpenAI para acceder a los modelos del gateway de 4Geeks; no usa LangChain ni LlamaIndex.

## Flujo de extremo a extremo

```text
Markdown de docs/company-knowledge-base/
             │
             ▼
 setup() ─ leer y preparar documentos / formar chunks
             │
             ├── embed(texto del chunk) ──► embedding de 4Geeks
             │                                      │
             └──────────────────────────────────────┘
                              │
                              ▼
              Qdrant: colección nexova_knowledge
                              │
Pregunta ──► POST /knowledge/query ──► query()
                                        │
                                        ├── retrieve()
                                        │     ├── embed(pregunta)
                                        │     ├── búsqueda vectorial en Qdrant
                                        │     └── filtrar por min_score
                                        │
                                        ├── contexto de chunks + pregunta
                                        │       └── prompt con reglas de negocio
                                        ├── LLM de generación de 4Geeks
                                        └── respuesta generada (solo texto)
```

1. **Fuentes.** `setup()` procesa los cuatro documentos Markdown versionados en `docs/company-knowledge-base/`: líneas de servicio, tarifas, SLA de contratación y manejo de objeciones.
2. **Preparación e indexación.** El preparador conserva texto y metadatos de origen (empresa, identificador del documento, sección, idioma e índice del chunk). `embed()` convierte cada texto en vector. `setup()` crea o actualiza la colección `nexova_knowledge` y carga los puntos en Qdrant usando IDs deterministas; la indexación es repetible sin duplicar los mismos puntos.
3. **Consulta HTTP.** El cliente envía `{ "question": "..." }` a `POST /knowledge/query`. El router delega en `data.pipelines.rag.query()`; no implementa recuperación ni generación por su cuenta.
4. **Recuperación.** `query()` llama a `retrieve()`. Esta usa el mismo `embed()` con la pregunta, pide hasta `k` puntos a Qdrant, restringe la búsqueda al conocimiento de Nexova y descarta resultados por debajo de `min_score`. El default de `retrieve()` es `k=5`; `query()` usa ese default salvo configuración/cambio explícito. La función puede devolver menos de `k` resultados o ninguno.
5. **Prompt y generación.** `generate_answer()` construye el contexto con los fragmentos recuperados y sus metadatos de fuente, junto con la pregunta. El prompt instruye al modelo a contestar con evidencia, no inventar condiciones comerciales, no ofrecer descuentos sobre el 22 %, presentar los plazos como promedios (no garantías) y reconocer cuando el contexto no basta.
6. **Respuesta.** El modelo de generación produce la respuesta final. La API devuelve únicamente `{ "answer": "..." }`; nunca expone payloads, chunks crudos ni scores de similitud al cliente.

## Chunking

La estrategia es **semántica e híbrida a nivel de Markdown**, no una división ciega cada N caracteres. El preparador reconoce encabezados para asignar la sección, y conserva como unidad cada párrafo, viñeta/regla o enunciado completo. Los puntos enumerados que explican líneas de servicio se mantienen como unidades de contenido; las reglas que contienen una condición y su consecuencia, y las objeciones con su respuesta, se preservan juntas siempre que caben en el límite configurado.

Esto encaja con el corpus, que es pequeño (cuatro documentos breves) y está compuesto principalmente por listas de precios, condiciones, SLA y pares objeción-respuesta. Buscar por unidad semántica permite encontrar, por ejemplo, la objeción junto con su respuesta y la restricción de descuento, en lugar de separar una regla de su excepción. Si una unidad indivisible supera el máximo permitido, el preparador la rechaza con error en vez de truncarla silenciosamente por la mitad.

El máximo de caracteres está definido por `MAX_CHUNK_CHARS` en el preparador. Las pruebas verifican que cada unidad no excede el máximo y que las viñetas y párrafos se mantienen. La colección consultada para la evaluación contiene **29 chunks**, distribuidos así: `hiring-process-sla`: 7; `objection-handling`: 4; `pricing-model`: 13; `service-lines`: 5. Este conteo es el observado en esa indexación y puede variar si cambian los documentos o el chunker.

## Embeddings y modelos

- **Proveedor:** modelos accesibles mediante el gateway de 4Geeks, según la configuración del proyecto.
- **Embeddings:** `madrid-spain/openrouter/perplexity/pplx-embed-v1-0.6b` (ID configurado para el gateway). Es un modelo dedicado a transformar texto en vectores; no se usa para redactar la respuesta.
- **Generación:** `madrid-spain/openrouter/deepseek/deepseek-v4-flash` (ID configurado para el gateway), seleccionado de forma independiente mediante `GENERATION_MODEL`.
- **Consistencia de `embed()`:** `setup()` llama a `embed()` sobre cada chunk al indexar; `retrieve()` llama a la misma implementación sobre la pregunta de consulta. Así ambos vectores usan el mismo modelo y la misma configuración de embedding. No se debe cambiar el modelo o el preprocesado sin reconstruir la colección, porque se rompería la compatibilidad del espacio vectorial.
- **Dimensión:** **1024**, verificada tanto en la configuración de la colección Qdrant como en la longitud de un vector real devuelto por `embed()`; ambas coinciden. Los tests pueden usar vectores simulados de otra dimensión, por lo que no se deben usar como medida del índice de producción.
- **Distancia:** coseno (`COSINE`) en Qdrant.
- **Preprocesado:** se embebe el texto del chunk preparado y, en consulta, la pregunta original. El código evita que el texto usado en retrieval difiera entre indexación y consulta en cuanto al modelo. No se aplica normalización lingüística adicional declarada en esta documentación; si se añade normalización, debe ser determinista y compartida por ambos caminos.

La configuración del contenedor permite pasar `QDRANT_URL`, `EMBEDDING_MODEL` y `GENERATION_MODEL` por entorno. Los valores secretos, en especial `LLM_API_KEY`, se suministran mediante `.env`/entorno y nunca se guardan en este documento.

## Recuperación y umbral

`retrieve(query, *, k=5, min_score=0.3, ...)` consulta la colección `nexova_knowledge`, filtra por `company=nexova`, solicita payloads sin vectores y elimina los resultados con score inferior a `min_score`. El umbral configurado es **0.30**. Se eligió para no descartar evidencia empresarial útil por una similitud moderada: durante la calibración manual, el fragmento correcto sobre la tarifa de headhunting puntuó aproximadamente **0.3418**, por lo que el umbral previo de 0.35 lo excluía y 0.30 permitió recuperarlo. El umbral debe revisarse si se cambia el modelo, la métrica, el corpus o el preprocesado.

La evaluación real con `scripts/evaluate_retrieval.py`, el conjunto `data/eval/test-queries.json` y `k=3` obtuvo **10/10 = 100 % Recall@3** (10 preguntas; mínimo requerido: 80 %). Este resultado mide ese conjunto y el estado de la colección al ejecutar la evaluación; no garantiza el mismo recall para consultas arbitrarias ni sustituye una nueva medición después de cambiar los datos o modelos.

## Generación y seguridad de respuestas

El contexto del prompt contiene los fragmentos recuperados, sus fuentes y la pregunta. Las instrucciones comerciales relevantes son:

- no inventar precios, plazos, políticas ni excepciones;
- no ofrecer descuentos sobre el 22 %; escalar su aprobación a Marcos Ibáñez;
- describir los tiempos de entrega como promedios, salvo condiciones contractuales explícitas;
- explicar insuficiencia de contexto cuando no se recupera evidencia pertinente;
- mantener transparencia sobre posibles trabajos previos con competidores.

El router FastAPI es una capa delgada: valida el cuerpo, invoca `query()` y devuelve solo la respuesta generada. La recuperación y la generación se mantienen en el pipeline para evitar lógica duplicada y permitir su prueba independiente.

## Cómo ejecutar y verificar

Desde la raíz del repositorio, con las variables de entorno configuradas y Qdrant disponible:

```powershell
# Iniciar Qdrant
docker compose up -d qdrant

# Indexar / reconstruir la base mediante el setup expuesto por el proyecto
uv run --env-file .env --group rag python -c "from data.process.rag import setup; print(setup())"

# Evaluar Recall@3 contra el conjunto local
uv run --env-file .env --group rag python scripts/evaluate_retrieval.py
```

La salida de `setup()` es la fuente de verdad para el total de documentos y chunks de una indexación concreta. La evaluación consulta Qdrant real y el gateway configurado; las pruebas unitarias, en cambio, usan stubs y no requieren esos servicios.
