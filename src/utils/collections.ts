import { AvailabilityStatus, Candidate, SeniorityLevel } from "../types/models";

/*Retorna candidatos que tienen TODAS las habilidades requeridas
El matching de habilidades debe ser case-insensitive*/
function filterCandidatesBySkills(candidates: Candidate[], requiredSkills: string[]): Candidate[] {
    return candidates.filter(c =>
        requiredSkills.every(skill =>
            c.skills.includes(skill)
        )
    )
}

//Retorna candidatos con el nivel de seniority especificado
function filterCandidatesBySeniority(candidates: Candidate[], seniority: SeniorityLevel): Candidate[] {
    return candidates.filter(c => c.seniority === seniority);
}

//Retorna candidatos cuya disponibilidad coincida con cualquiera de los estados proporcionados
function filterCandidatesByAvailability(candidates: Candidate[], availability: AvailabilityStatus[]): Candidate[] {
    return candidates.filter(c => availability.includes(c.availability));
}

/*Retorna candidatos ordenados por salario esperado (ascendente o descendente)
No debe mutar el array original*/
function sortCandidatesBySalary(candidates: Candidate[], order: "asc" | "desc"): Candidate[] {
    return [...candidates].sort((a, b) =>
        order === "asc" ? a.expectedSalary - b.expectedSalary : b.expectedSalary - a.expectedSalary
    );
}

/*Retorna candidatos ordenados por años de experiencia
No debe mutar el array original*/
function sortCandidatesByExperience(candidates: Candidate[], order: "asc" | "desc"): Candidate[]{
    return [...candidates].sort((a, b) =>
        order === "asc" ? a.yearsOfExperience - b.yearsOfExperience : b.yearsOfExperience - a.yearsOfExperience
    );
}



