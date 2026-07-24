export type TalentFormData = {
  nombreCompleto: string;
  email: string;
  telefono: string;
  pais: string;
  aniosExperiencia: string;
  sector: string;
  nivelIngles: string;
  disponibilidad: string;
  linkedin: string;
  comentarios: string;
  aceptaPolitica: boolean;
};

export type TalentFormErrors = Partial<Record<keyof TalentFormData, string>>;

const phoneRegex = /^\+\d{1,4}[\s\d-]{6,20}$/;

export function validateTalentForm(data: TalentFormData): TalentFormErrors {
  const errors: TalentFormErrors = {};

  if (data.nombreCompleto.trim().split(/\s+/).filter(Boolean).length < 2) {
    errors.nombreCompleto = "El nombre debe contener al menos nombre y apellido";
  }

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) {
    errors.email = "Ingresa un email valido (ejemplo: nombre@empresa.com)";
  }

  if (!phoneRegex.test(data.telefono.trim())) {
    errors.telefono =
      "El telefono debe incluir codigo de pais (ejemplo: +34 612 345 678)";
  }

  if (!data.pais) {
    errors.pais = "Selecciona tu pais de residencia";
  }

  const years = Number(data.aniosExperiencia);
  if (!Number.isFinite(years) || years < 0 || years > 50) {
    errors.aniosExperiencia =
      "Los anos de experiencia deben estar entre 0 y 50";
  }

  if (!data.sector) {
    errors.sector = "Selecciona el sector de tu interes";
  }

  if (!data.nivelIngles) {
    errors.nivelIngles = "Indica tu nivel de ingles";
  }

  if (!data.disponibilidad) {
    errors.disponibilidad = "Selecciona tu disponibilidad";
  }

  if (data.linkedin.trim() && !/^https?:\/\/.+/.test(data.linkedin.trim())) {
    errors.linkedin = "Si incluyes LinkedIn, debe ser una URL valida";
  }

  if (data.comentarios.length > 500) {
    errors.comentarios =
      `Los comentarios no pueden exceder 500 caracteres (quedan ${500 - data.comentarios.length})`;
  }

  if (!data.aceptaPolitica) {
    errors.aceptaPolitica =
      "Debes aceptar la politica de tratamiento de datos para continuar";
  }

  return errors;
}
