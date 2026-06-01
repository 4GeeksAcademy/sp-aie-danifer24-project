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
	const normalizedCandidateSkills = candidate.skills.map(skill => skill.toLowerCase());
	const requiredSkills = vacancy.requiredSkills.map(skill => skill.toLowerCase());
	const preferredSkills = vacancy.preferredSkills.map(skill => skill.toLowerCase());

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
	const years = candidate.yearsOfExperience;

	if (years >= vacancy.minYearsExperience && years <= vacancy.maxYearsExperience) {
		return 20;
	}

	const distanceToRange = years < vacancy.minYearsExperience
		? vacancy.minYearsExperience - years
		: years - vacancy.maxYearsExperience;

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
	const expectedSalary = candidate.expectedSalary;

	if (expectedSalary >= vacancy.salaryRangeMin && expectedSalary <= vacancy.salaryRangeMax) {
		return 10;
	}

	if (expectedSalary > vacancy.salaryRangeMax && expectedSalary <= vacancy.salaryRangeMax * 1.2) {
		return 5;
	}

	return 0;
}

function calculateCandidateScore(candidate: Candidate, vacancy: Vacancy): number {
	const rawScore = getSkillsScore(candidate, vacancy)
		+ getExperienceScore(candidate, vacancy)
		+ getSeniorityScore(candidate, vacancy)
		+ getEnglishScore(candidate, vacancy)
		+ getSalaryScore(candidate, vacancy);

	return Math.min(100, rawScore);
}

function rankCandidatesForVacancy(candidates: Candidate[], vacancy: Vacancy): Array<{ candidate: Candidate; score: number }> {
	return candidates
		.map(candidate => ({
			candidate,
			score: calculateCandidateScore(candidate, vacancy),
		}))
		.sort((a, b) => b.score - a.score);
}

function groupCandidatesBySeniority(candidates: Candidate[]): Record<SeniorityLevel, Candidate[]> {
	const groupedCandidates: Record<SeniorityLevel, Candidate[]> = {
		"Junior": [],
		"Semi-Senior": [],
		"Senior": [],
		"Lead": [],
		"Executive": [],
	};

	for (const candidate of candidates) {
		groupedCandidates[candidate.seniority].push(candidate);
	}

	return groupedCandidates;
}

// Aggregations and Reports

function countCandidatesByStatus(candidates: Candidate[]): Record<CandidateStatus, number> {
	const countsByStatus: Record<CandidateStatus, number> = {
		"Active": 0,
		"In process": 0,
		"Hired": 0,
		"Inactive": 0,
	};

	for (const candidate of candidates) {
		countsByStatus[candidate.status] += 1;
	}

	return countsByStatus;
}

function calculateAverageSalary(candidates: Candidate[]): number {
	if (candidates.length === 0) {
		return 0;
	}

	const totalSalary = candidates.reduce((sum, candidate) => sum + candidate.expectedSalary, 0);
	const average = totalSalary / candidates.length;

	return Number(average.toFixed(2));
}

function findTopSkills(candidates: Candidate[], topN: number): Array<{ skill: string; count: number }> {
	if (topN <= 0) {
		return [];
	}

	const skillStats = new Map<string, { skill: string; count: number }>();

	for (const candidate of candidates) {
		const uniqueCandidateSkills = new Set(candidate.skills.map(skill => skill.trim()).filter(Boolean));

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

function calculateVacancyFillRate(processes: SelectionProcess[]): number {
	if (processes.length === 0) {
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