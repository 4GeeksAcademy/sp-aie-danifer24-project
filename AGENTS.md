# AGENTS

## Lectura obligatoria al inicio de cada sesion

Antes de proponer cambios o tocar codigo, el agente debe leer estos archivos del banco de memoria:

1. memory-bank/projectbrief.md
2. memory-bank/techContext.md
3. memory-bank/progress.md

Si alguno esta vacio o desactualizado, el agente debe advertirlo y proponer su actualizacion antes de avanzar con cambios grandes.

## Flujo obligatorio antes de cada commit

El agente debe seguir este flujo, en orden, antes de crear cualquier commit:

1. Verificar estado del repositorio con git status y confirmar que entiende que archivos fueron cambiados.
2. Revisar el diff completo de los archivos tocados y validar que no haya cambios accidentales o fuera de alcance.
3. Ejecutar validaciones del proyecto afectado (minimo lint y pruebas disponibles; si no hay pruebas, documentarlo).
4. Confirmar que la implementacion cumple el alcance funcional solicitado y no rompe criterios previos.
5. Actualizar memory-bank/progress.md con estado real del avance y siguientes pasos.
6. Proponer mensaje de commit claro y pedir confirmacion explicita del desarrollador antes de ejecutar git commit.

Si falla cualquier paso, no se debe commitear.

## Archivos y carpetas protegidos (no modificar sin confirmacion explicita)

El agente no debe modificar estos recursos sin autorizacion explicita del desarrollador en la conversacion activa:

1. Todos los archivos CONTEXT del repositorio: CONTEXT.md, CONTEXT-HITO1.md, CONTEXT-HITO2.md, CONTEXT-HITO3.md.
2. Este archivo de politica: AGENTS.md.
3. Configuracion de workspace y herramientas base: package.json (raiz), apps/talent-pipeline-tracker/package.json, tsconfig.json, eslint.config.mjs, next.config.ts.
4. Carpetas de infraestructura y operaciones: infra/, workflows/, mcps/, internal/.
5. Documentacion estrategica del banco de memoria: memory-bank/projectbrief.md y memory-bank/techContext.md.

Excepcion: memory-bank/progress.md si puede actualizarse sin confirmacion previa cuando el cambio sea solo para reflejar avance real del trabajo realizado.
