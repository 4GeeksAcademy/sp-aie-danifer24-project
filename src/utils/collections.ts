import { AvailabilityStatus, Candidate, SeniorityLevel } from "../types/models";

/*Retorna candidatos que tienen TODAS las habilidades requeridas
El matching de habilidades debe ser case-insensitive*/
function filterCandidatesBySkills(candidates: Candidate[] | null | undefined, requiredSkills: string[] | null | undefined): Candidate[] {
    if (!Array.isArray(candidates)) {
        return [];
    }

    const safeRequiredSkills = Array.isArray(requiredSkills) ? requiredSkills : [];

    return candidates.filter(c => {
        const normalizedSkills = Array.isArray(c.skills) ? c.skills.map(skill => skill.toLowerCase()) : [];

        return safeRequiredSkills.every(skill =>
            normalizedSkills.includes(skill.toLowerCase())
        );
    });
}

//Retorna candidatos con el nivel de seniority especificado
function filterCandidatesBySeniority(candidates: Candidate[] | null | undefined, seniority: SeniorityLevel): Candidate[] {
    if (!Array.isArray(candidates)) {
        return [];
    }

    return candidates.filter(c => c.seniority === seniority);
}

//Retorna candidatos cuya disponibilidad coincida con cualquiera de los estados proporcionados
function filterCandidatesByAvailability(candidates: Candidate[] | null | undefined, availability: AvailabilityStatus[] | null | undefined): Candidate[] {
    if (!Array.isArray(candidates)) {
        return [];
    }

    const safeAvailability = Array.isArray(availability) ? availability : [];

    return candidates.filter(c => safeAvailability.includes(c.availability));
}

/*Retorna candidatos ordenados por salario esperado (ascendente o descendente)
No debe mutar el array original*/
function sortCandidatesBySalary(candidates: Candidate[] | null | undefined, order: "asc" | "desc"): Candidate[] {
    if (!Array.isArray(candidates)) {
        return [];
    }

    return [...candidates].sort((a, b) =>
        order === "asc"
            ? (Number.isFinite(a.expectedSalary) ? a.expectedSalary : 0) - (Number.isFinite(b.expectedSalary) ? b.expectedSalary : 0)
            : (Number.isFinite(b.expectedSalary) ? b.expectedSalary : 0) - (Number.isFinite(a.expectedSalary) ? a.expectedSalary : 0)
    );
}

/*Retorna candidatos ordenados por años de experiencia
No debe mutar el array original*/
function sortCandidatesByExperience(candidates: Candidate[] | null | undefined, order: "asc" | "desc"): Candidate[] {
    if (!Array.isArray(candidates)) {
        return [];
    }

    return [...candidates].sort((a, b) =>
        order === "asc"
            ? (Number.isFinite(a.yearsOfExperience) ? a.yearsOfExperience : 0) - (Number.isFinite(b.yearsOfExperience) ? b.yearsOfExperience : 0)
            : (Number.isFinite(b.yearsOfExperience) ? b.yearsOfExperience : 0) - (Number.isFinite(a.yearsOfExperience) ? a.yearsOfExperience : 0)
    );
}

export {
    filterCandidatesBySkills,
    filterCandidatesBySeniority,
    filterCandidatesByAvailability,
    sortCandidatesBySalary,
    sortCandidatesByExperience,
};



