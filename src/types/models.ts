interface Candidate {
  id: string; // Identificador único (ej: "C-2024-0451")
  fullName: string; // Nombre completo
  email: string; // Email de contacto
  phone: string; // Teléfono de contacto
  yearsOfExperience: number; // Años totales de experiencia profesional
  skills: string[]; // Array de habilidades (ej: ["TypeScript", "React", "Node.js"])
  englishLevel: EnglishLevel; // Nivel de inglés
  seniority: SeniorityLevel; // Nivel profesional
  currentSalary: number; // Salario actual en USD
  expectedSalary: number; // Salario esperado en USD
  availability: AvailabilityStatus; // Disponibilidad actual
  location: string; // Ciudad y país (ej: "Valencia, España")
  remoteOnly: boolean; // Solo acepta posiciones remotas
  status: CandidateStatus; // Estado actual en la base de datos
}

type EnglishLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "Native";
type SeniorityLevel =
  | "Junior"
  | "Semi-Senior"
  | "Senior"
  | "Lead"
  | "Executive";
type AvailabilityStatus = "Immediate" | "2 weeks" | "1 month" | "Not available";
type CandidateStatus = "Active" | "In process" | "Hired" | "Inactive";

interface Vacancy {
  id: string; // Identificador único (ej: "V-2024-0892")
  title: string; // Título del puesto (ej: "Senior Full-Stack Developer")
  companyName: string; // Nombre de la empresa cliente
  requiredSkills: string[]; // Habilidades técnicas requeridas
  preferredSkills: string[]; // Habilidades deseables
  minYearsExperience: number; // Experiencia mínima requerida
  maxYearsExperience: number; // Experiencia máxima relevante
  requiredEnglishLevel: EnglishLevel; // Nivel mínimo de inglés
  requiredSeniority: SeniorityLevel; // Nivel de seniority requerido
  salaryRangeMin: number; // Salario mínimo ofrecido (USD)
  salaryRangeMax: number; // Salario máximo ofrecido (USD)
  isRemote: boolean; // Posición remota
  location: string; // Ubicación de oficina si no es remota
  status: VacancyStatus; // Estado actual de la vacante
}

type VacancyStatus = "Open" | "In progress" | "Closed" | "On hold";

interface SelectionProcess {
  id: string; // Identificador único (ej: "SP-2024-1523")
  candidateId: string; // Referencia al candidato
  vacancyId: string; // Referencia a la vacante
  stage: ProcessStage; // Etapa actual
  score: number; // Puntaje de match (0-100)
  notes: string; // Notas del consultor
  createdAt: Date; // Fecha de inicio del proceso
  updatedAt: Date; // Fecha de última actualización
}

type ProcessStage =
  | "Screening"
  | "Interview"
  | "Technical test"
  | "Final interview"
  | "Offer"
  | "Rejected"
  | "Hired";

export type {
  Candidate,
  EnglishLevel,
  SeniorityLevel,
  AvailabilityStatus,
  CandidateStatus,
  Vacancy,
  VacancyStatus,
  SelectionProcess,
  ProcessStage,
};