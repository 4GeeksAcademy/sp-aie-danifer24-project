import {
	AvailabilityStatus,
	Candidate,
	CandidateStatus,
	EnglishLevel,
	SeniorityLevel,
	Vacancy,
	VacancyStatus,
} from "../types/models";

const ENGLISH_LEVELS: EnglishLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2", "Native"];
const SENIORITY_LEVELS: SeniorityLevel[] = ["Junior", "Semi-Senior", "Senior", "Lead", "Executive"];
const AVAILABILITY_STATUSES: AvailabilityStatus[] = ["Immediate", "2 weeks", "1 month", "Not available"];
const CANDIDATE_STATUSES: CandidateStatus[] = ["Active", "In process", "Hired", "Inactive"];
const VACANCY_STATUSES: VacancyStatus[] = ["Open", "In progress", "Closed", "On hold"];

function isValidEmail(email: string): boolean {
	const normalizedEmail = email.trim();
	const atIndex = normalizedEmail.indexOf("@");
	const lastDotIndex = normalizedEmail.lastIndexOf(".");

	if (atIndex <= 0) {
		return false;
	}

	if (lastDotIndex <= atIndex + 1) {
		return false;
	}

	if (lastDotIndex === normalizedEmail.length - 1) {
		return false;
	}

	return normalizedEmail.indexOf("@", atIndex + 1) === -1;
}

function validateCandidate(candidate: Candidate): { valid: boolean; errors: string[] } {
	const errors: string[] = [];

	if (!candidate.id?.trim()) {
		errors.push("El ID del candidato es obligatorio.");
	}

	if (!candidate.fullName?.trim()) {
		errors.push("El nombre completo del candidato es obligatorio.");
	}

	if (!candidate.email?.trim() || !isValidEmail(candidate.email)) {
		errors.push("El email del candidato no es valido.");
	}

	if (!candidate.phone?.trim()) {
		errors.push("El telefono del candidato es obligatorio.");
	}

	if (!Number.isFinite(candidate.yearsOfExperience) || candidate.yearsOfExperience < 0) {
		errors.push("Los anos de experiencia deben ser un numero mayor o igual a 0.");
	}

	if (!Array.isArray(candidate.skills) || candidate.skills.length === 0) {
		errors.push("El candidato debe tener al menos una habilidad.");
	}

	if (!ENGLISH_LEVELS.includes(candidate.englishLevel)) {
		errors.push("El nivel de ingles del candidato no es valido.");
	}

	if (!SENIORITY_LEVELS.includes(candidate.seniority)) {
		errors.push("El seniority del candidato no es valido.");
	}

	if (!Number.isFinite(candidate.currentSalary) || candidate.currentSalary < 0) {
		errors.push("El salario actual debe ser un numero mayor o igual a 0.");
	}

	if (!Number.isFinite(candidate.expectedSalary) || candidate.expectedSalary < 0) {
		errors.push("El salario esperado debe ser un numero mayor o igual a 0.");
	}

	if (candidate.expectedSalary < candidate.currentSalary) {
		errors.push("El salario esperado no puede ser menor al salario actual.");
	}

	if (!AVAILABILITY_STATUSES.includes(candidate.availability)) {
		errors.push("La disponibilidad del candidato no es valida.");
	}

	if (!candidate.location?.trim()) {
		errors.push("La ubicacion del candidato es obligatoria.");
	}

	if (!CANDIDATE_STATUSES.includes(candidate.status)) {
		errors.push("El estado del candidato no es valido.");
	}

	return {
		valid: errors.length === 0,
		errors,
	};
}

function validateVacancy(vacancy: Vacancy): { valid: boolean; errors: string[] } {
	const errors: string[] = [];

	if (!vacancy.id?.trim()) {
		errors.push("El ID de la vacante es obligatorio.");
	}

	if (!vacancy.title?.trim()) {
		errors.push("El titulo de la vacante es obligatorio.");
	}

	if (!vacancy.companyName?.trim()) {
		errors.push("El nombre de la empresa es obligatorio.");
	}

	if (!Array.isArray(vacancy.requiredSkills) || vacancy.requiredSkills.length === 0) {
		errors.push("La vacante debe tener al menos una habilidad requerida.");
	}

	if (!Array.isArray(vacancy.preferredSkills)) {
		errors.push("Las habilidades deseables deben definirse como un array.");
	}

	if (!Number.isFinite(vacancy.minYearsExperience) || vacancy.minYearsExperience < 0) {
		errors.push("La experiencia minima debe ser un numero mayor o igual a 0.");
	}

	if (!Number.isFinite(vacancy.maxYearsExperience) || vacancy.maxYearsExperience < 0) {
		errors.push("La experiencia maxima debe ser un numero mayor o igual a 0.");
	}

	if (vacancy.maxYearsExperience < vacancy.minYearsExperience) {
		errors.push("La experiencia maxima no puede ser menor que la minima.");
	}

	if (!ENGLISH_LEVELS.includes(vacancy.requiredEnglishLevel)) {
		errors.push("El nivel de ingles requerido no es valido.");
	}

	if (!SENIORITY_LEVELS.includes(vacancy.requiredSeniority)) {
		errors.push("El seniority requerido no es valido.");
	}

	if (!Number.isFinite(vacancy.salaryRangeMin) || vacancy.salaryRangeMin < 0) {
		errors.push("El salario minimo debe ser un numero mayor o igual a 0.");
	}

	if (!Number.isFinite(vacancy.salaryRangeMax) || vacancy.salaryRangeMax < 0) {
		errors.push("El salario maximo debe ser un numero mayor o igual a 0.");
	}

	if (vacancy.salaryRangeMax < vacancy.salaryRangeMin) {
		errors.push("El salario maximo no puede ser menor que el salario minimo.");
	}

	if (!vacancy.isRemote && !vacancy.location?.trim()) {
		errors.push("La ubicacion es obligatoria para vacantes no remotas.");
	}

	if (!VACANCY_STATUSES.includes(vacancy.status)) {
		errors.push("El estado de la vacante no es valido.");
	}

	return {
		valid: errors.length === 0,
		errors,
	};
}

export { validateCandidate, validateVacancy, isValidEmail };
