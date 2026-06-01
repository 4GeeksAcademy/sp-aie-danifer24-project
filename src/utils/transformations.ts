import { Candidate, CandidateStatus, EnglishLevel, SelectionProcess, SeniorityLevel, Vacancy } from "../types/models";

// Scoring & Matching

const SENIORITY_ORDER: SeniorityLevel[] = [
	"Junior",
	"Semi-Senior",
	"Senior",
	"Lead",
	"Executive",
];

const ENGLISH_LEVEL_ORDER: EnglishLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2", "Native"];

function getSkillsScore(candidate: Candidate, vacancy: Vacancy): number {
	const normalizedCandidateSkills = Array.isArray(candidate.skills)
		? candidate.skills.map(skill => skill.toLowerCase())
		: [];
	const requiredSkills = Array.isArray(vacancy.requiredSkills)
		? vacancy.requiredSkills.map(skill => skill.toLowerCase())
		: [];
	const preferredSkills = Array.isArray(vacancy.preferredSkills)
		? vacancy.preferredSkills.map(skill => skill.toLowerCase())
		: [];

	let score = 0;

	const matchedRequiredSkills = requiredSkills.filter(skill => normalizedCandidateSkills.includes(skill)).length;

	if (requiredSkills.length === 0 || matchedRequiredSkills === requiredSkills.length) {
		score += 40;
	} else if (matchedRequiredSkills / requiredSkills.length >= 0.5) {
		score += 20;
	}

	const matchedPreferredSkills = preferredSkills.filter(skill => normalizedCandidateSkills.includes(skill)).length;
	score += Math.min(matchedPreferredSkills * 10, 20);

	return score;
}

function getExperienceScore(candidate: Candidate, vacancy: Vacancy): number {
	const years = Number.isFinite(candidate.yearsOfExperience) ? candidate.yearsOfExperience : 0;
	const minYears = Number.isFinite(vacancy.minYearsExperience) ? vacancy.minYearsExperience : 0;
	const maxYears = Number.isFinite(vacancy.maxYearsExperience) ? vacancy.maxYearsExperience : 0;

	if (years >= minYears && years <= maxYears) {
		return 20;
	}

	const distanceToRange = years < minYears
		? minYears - years
		: years - maxYears;

	return distanceToRange <= 2 ? 10 : 0;
}

function getSeniorityScore(candidate: Candidate, vacancy: Vacancy): number {
	const candidateLevel = SENIORITY_ORDER.indexOf(candidate.seniority);
	const vacancyLevel = SENIORITY_ORDER.indexOf(vacancy.requiredSeniority);

	if (candidateLevel === vacancyLevel) {
		return 15;
	}

	return Math.abs(candidateLevel - vacancyLevel) === 1 ? 7 : 0;
}

function getEnglishScore(candidate: Candidate, vacancy: Vacancy): number {
	const candidateLevel = ENGLISH_LEVEL_ORDER.indexOf(candidate.englishLevel);
	const requiredLevel = ENGLISH_LEVEL_ORDER.indexOf(vacancy.requiredEnglishLevel);

	return candidateLevel >= requiredLevel ? 15 : 0;
}

function getSalaryScore(candidate: Candidate, vacancy: Vacancy): number {
	const expectedSalary = Number.isFinite(candidate.expectedSalary) ? candidate.expectedSalary : 0;
	const salaryMin = Number.isFinite(vacancy.salaryRangeMin) ? vacancy.salaryRangeMin : 0;
	const salaryMax = Number.isFinite(vacancy.salaryRangeMax) ? vacancy.salaryRangeMax : 0;

	if (expectedSalary >= salaryMin && expectedSalary <= salaryMax) {
		return 10;
	}

	if (expectedSalary > salaryMax && expectedSalary <= salaryMax * 1.2) {
		return 5;
	}

	return 0;
}

function calculateCandidateScore(candidate: Candidate | null | undefined, vacancy: Vacancy | null | undefined): number {
	if (!candidate || !vacancy) {
		return 0;
	}

	const rawScore = getSkillsScore(candidate, vacancy)
		+ getExperienceScore(candidate, vacancy)
		+ getSeniorityScore(candidate, vacancy)
		+ getEnglishScore(candidate, vacancy)
		+ getSalaryScore(candidate, vacancy);

	return Math.min(100, rawScore);
}

function rankCandidatesForVacancy(candidates: Candidate[] | null | undefined, vacancy: Vacancy | null | undefined): Array<{ candidate: Candidate; score: number }> {
	if (!Array.isArray(candidates) || !vacancy) {
		return [];
	}

	return candidates
		.map(candidate => ({
			candidate,
			score: calculateCandidateScore(candidate, vacancy),
		}))
		.sort((a, b) => b.score - a.score);
}

function groupCandidatesBySeniority(candidates: Candidate[] | null | undefined): Record<SeniorityLevel, Candidate[]> {
	const groupedCandidates: Record<SeniorityLevel, Candidate[]> = {
		"Junior": [],
		"Semi-Senior": [],
		"Senior": [],
		"Lead": [],
		"Executive": [],
	};

	if (!Array.isArray(candidates)) {
		return groupedCandidates;
	}

	for (const candidate of candidates) {
		groupedCandidates[candidate.seniority].push(candidate);
	}

	return groupedCandidates;
}

// Aggregations and Reports

function countCandidatesByStatus(candidates: Candidate[] | null | undefined): Record<CandidateStatus, number> {
	const countsByStatus: Record<CandidateStatus, number> = {
		"Active": 0,
		"In process": 0,
		"Hired": 0,
		"Inactive": 0,
	};

	if (!Array.isArray(candidates)) {
		return countsByStatus;
	}

	for (const candidate of candidates) {
		countsByStatus[candidate.status] += 1;
	}

	return countsByStatus;
}

function calculateAverageSalary(candidates: Candidate[] | null | undefined): number {
	if (!Array.isArray(candidates) || candidates.length === 0) {
		return 0;
	}

	const totalSalary = candidates.reduce(
		(sum, candidate) => sum + (Number.isFinite(candidate.expectedSalary) ? candidate.expectedSalary : 0),
		0
	);
	const average = totalSalary / candidates.length;

	return Number(average.toFixed(2));
}

function findTopSkills(candidates: Candidate[] | null | undefined, topN: number): Array<{ skill: string; count: number }> {
	if (!Array.isArray(candidates) || topN <= 0) {
		return [];
	}

	const skillStats = new Map<string, { skill: string; count: number }>();

	for (const candidate of candidates) {
		const uniqueCandidateSkills = new Set(
			(Array.isArray(candidate.skills) ? candidate.skills : []).map(skill => skill.trim()).filter(Boolean)
		);

		for (const rawSkill of uniqueCandidateSkills) {
			const normalizedSkill = rawSkill.toLowerCase();
			const current = skillStats.get(normalizedSkill);

			if (!current) {
				skillStats.set(normalizedSkill, { skill: rawSkill, count: 1 });
				continue;
			}

			current.count += 1;
		}
	}

	return Array.from(skillStats.values())
		.sort((a, b) => b.count - a.count || a.skill.localeCompare(b.skill))
		.slice(0, topN);
}

function calculateVacancyFillRate(processes: SelectionProcess[] | null | undefined): number {
	if (!Array.isArray(processes) || processes.length === 0) {
		return 0;
	}

	const hiredCount = processes.filter(process => process.stage === "Hired").length;
	const fillRate = (hiredCount / processes.length) * 100;

	return Number(fillRate.toFixed(2));
}

export {
	calculateCandidateScore,
	rankCandidatesForVacancy,
	groupCandidatesBySeniority,
	countCandidatesByStatus,
	calculateAverageSalary,
	findTopSkills,
	calculateVacancyFillRate,
};