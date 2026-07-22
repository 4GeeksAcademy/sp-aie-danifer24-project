---
title: "Validación previa a cambios"
description: "Asegura revisión de contexto, alcance y validaciones antes de implementar cambios de código."
scope: user
alwaysApply: true
---

# Validación previa a cambios

## Ámbito de aplicación

- Tipo: siempre activa

## Directriz

Antes de proponer o implementar cambios de código, revisar primero el contexto mínimo del proyecto y confirmar que el cambio está dentro del alcance solicitado.

## Lista de verificación obligatoria

1. Leer archivos de contexto requeridos por políticas del repositorio.
2. Verificar que no se modifiquen archivos protegidos sin confirmación explícita.
3. Limitar cambios al objetivo solicitado, evitando ediciones no relacionadas.
4. Validar resultado (lint, pruebas o verificación funcional aplicable) antes de cerrar la tarea.