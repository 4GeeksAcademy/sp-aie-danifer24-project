import { Candidate } from "../types/models";

/*Realiza búsqueda lineal para encontrar un candidato por ID
Retorna el candidato si se encuentra, null en caso contrario*/
function findCandidateById(candidates: Candidate[], id: string): Candidate | null {
    for (const candidate of candidates) {
        if (candidate.id === id) {
            return candidate;
        }
    }
    return null;
}

/*Realiza búsqueda lineal para encontrar un candidato por email
La comparación de email debe ser case-insensitive
Retorna el candidato si se encuentra, null en caso contrario*/
function findCandidateByEmail(candidates: Candidate[], email: string): Candidate | null {
    for (const candidate of candidates) {
        if (candidate.email.toLowerCase() === email.toLowerCase()) {
            return candidate;
        }
    }
    return null;
}

/*Asume que el array ya está ordenado por salario esperado (ascendente)
Realiza búsqueda binaria para encontrar el índice de un candidato con el salario objetivo
Retorna el índice si se encuentra, -1 en caso contrario
Nota: Si múltiples candidatos tienen el mismo salario, retorna cualquier índice válido*/
function binarySearchCandidateBySalary(sortedCandidates: Candidate[], targetSalary: number): number {
    let left = 0;
    let right = sortedCandidates.length - 1;

    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        const midSalary = sortedCandidates[mid].expectedSalary;

        if (midSalary === targetSalary) {
            return mid;
        }

        if (midSalary < targetSalary) {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }

    return -1;
}

export { findCandidateById, findCandidateByEmail, binarySearchCandidateBySalary };



