import type { CreateFormData, CreateFormErrors } from "@/types/forms";

export function validateCreateCandidateForm(values: CreateFormData): CreateFormErrors {
  const nextErrors: CreateFormErrors = {};

  if (!values.full_name.trim()) nextErrors.full_name = "El nombre es obligatorio.";

  const email = values.email.trim();
  if (!email) nextErrors.email = "El email es obligatorio.";
  else if (!/^\S+@\S+\.\S+$/.test(email)) nextErrors.email = "El email no es válido.";

  if (!values.phone.trim()) nextErrors.phone = "El teléfono es obligatorio.";
  if (!values.position.trim()) nextErrors.position = "El puesto es obligatorio.";

  if (!values.experience_years.trim()) {
    nextErrors.experience_years = "Los años de experiencia son obligatorios.";
  } else {
    const years = Number(values.experience_years);
    if (!Number.isFinite(years) || years < 0) {
      nextErrors.experience_years = "Introduce un número válido (0 o más).";
    }
  }

  return nextErrors;
}
