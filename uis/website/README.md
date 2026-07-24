# Nexova Website (Hito 1)

Migracion del Hito 1 a Next.js + TypeScript.

## Alcance

- Landing corporativa en la ruta `/`.
- Formulario de registro de talento en `/talento`.
- Validaciones de formulario en TypeScript (`lib/validation.ts`).
- Marcado Schema.org de organizacion en la landing.

## Comandos

```bash
npm install
npm run dev
npm run lint
npm run build
```

## Estructura principal

- `app/page.tsx`: landing corporativa.
- `app/talento/page.tsx`: pagina del formulario de talento.
- `components/TalentForm.tsx`: formulario y estados de UI.
- `lib/validation.ts`: reglas de validacion y mensajes.
- `app/globals.css`: estilos globales.
