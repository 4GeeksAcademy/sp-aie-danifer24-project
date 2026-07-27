"use client";

import { useMemo, useState } from "react";
import { sampleCandidates, sampleProcesses, sampleVacancy } from "@/lib/sample-data";
import {
  filterCandidatesByAvailability,
  filterCandidatesBySeniority,
  filterCandidatesBySkills,
  sortCandidatesByExperience,
  sortCandidatesBySalary,
} from "@legacy/utils/collections";
import { findCandidateByEmail, findCandidateById } from "@legacy/utils/search";
import {
  calculateAverageSalary,
  calculateCandidateScore,
  calculateVacancyFillRate,
  countCandidatesByStatus,
  findTopSkills,
  groupCandidatesBySeniority,
  rankCandidatesForVacancy,
} from "@legacy/utils/transformations";
import { validateCandidate, validateVacancy } from "@legacy/utils/validations";

function toJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function TestingPlayground() {
  const initialOutput = useMemo(
    () => ({ sampleCandidates, sampleVacancy, sampleProcesses }),
    [],
  );
  const [label, setLabel] = useState("Datos iniciales");
  const [result, setResult] = useState<string>(toJson(initialOutput));

  function show(name: string, payload: unknown) {
    setLabel(name);
    setResult(toJson(payload));
  }

  return (
    <section className="playground-grid">
      <article className="panel">
        <div className="panel-header">
          <h2>Controles de Validacion</h2>
          <button
            className="btn btn-outline"
            onClick={() => show("Listo", { message: "Salida limpia" })}
            type="button"
          >
            Limpiar salida
          </button>
        </div>

        <div className="groups-grid">
          <div className="group-card">
            <h3>Busqueda / Filtros</h3>
            <button className="btn btn-dark" onClick={() => show("findCandidateById", findCandidateById(sampleCandidates, "C-2024-0452"))} type="button">Buscar por ID C-2024-0452</button>
            <button className="btn btn-dark" onClick={() => show("findCandidateByEmail", findCandidateByEmail(sampleCandidates, "carolina.silva@email.com"))} type="button">Buscar por email de Carolina</button>
            <button className="btn btn-amber" onClick={() => show("filterCandidatesBySkills", filterCandidatesBySkills(sampleCandidates, ["TypeScript", "Node.js"]))} type="button">Filtrar skills TypeScript + Node.js</button>
            <button className="btn btn-amber" onClick={() => show("filterCandidatesBySeniority", filterCandidatesBySeniority(sampleCandidates, "Senior"))} type="button">Filtrar seniority Senior</button>
            <button className="btn btn-amber" onClick={() => show("filterCandidatesByAvailability", filterCandidatesByAvailability(sampleCandidates, ["Immediate", "2 weeks"]))} type="button">Filtrar disponibilidad Immediate/2 weeks</button>
          </div>

          <div className="group-card">
            <h3>Ordenamiento</h3>
            <button className="btn btn-cyan" onClick={() => show("sortCandidatesBySalary asc", sortCandidatesBySalary(sampleCandidates, "asc"))} type="button">Ordenar salario asc</button>
            <button className="btn btn-cyan" onClick={() => show("sortCandidatesBySalary desc", sortCandidatesBySalary(sampleCandidates, "desc"))} type="button">Ordenar salario desc</button>
            <button className="btn btn-cyan" onClick={() => show("sortCandidatesByExperience desc", sortCandidatesByExperience(sampleCandidates, "desc"))} type="button">Ordenar experiencia desc</button>
          </div>

          <div className="group-card">
            <h3>Scoring / Matching</h3>
            <button className="btn btn-rose" onClick={() => show("calculateCandidateScore", { candidate: sampleCandidates[0].fullName, vacancy: sampleVacancy.title, score: calculateCandidateScore(sampleCandidates[0], sampleVacancy) })} type="button">Score Maria vs vacante</button>
            <button className="btn btn-rose" onClick={() => show("rankCandidatesForVacancy", rankCandidatesForVacancy(sampleCandidates, sampleVacancy))} type="button">Ranking de candidatos</button>
            <button className="btn btn-rose" onClick={() => show("groupCandidatesBySeniority", groupCandidatesBySeniority(sampleCandidates))} type="button">Agrupar por seniority</button>
          </div>

          <div className="group-card">
            <h3>Validaciones / Reportes</h3>
            <button
              className="btn btn-emerald"
              onClick={() => {
                const invalidCandidate = {
                  ...sampleCandidates[0],
                  email: "maria.email.com",
                  expectedSalary: -1,
                };
                show("validateCandidate", {
                  validCandidate: validateCandidate(sampleCandidates[0]),
                  invalidCandidate: validateCandidate(invalidCandidate),
                });
              }}
              type="button"
            >
              Validar candidato (ok + error)
            </button>
            <button
              className="btn btn-emerald"
              onClick={() => {
                const invalidVacancy = {
                  ...sampleVacancy,
                  salaryRangeMin: 7000,
                  salaryRangeMax: 6500,
                };
                show("validateVacancy", {
                  validVacancy: validateVacancy(sampleVacancy),
                  invalidVacancy: validateVacancy(invalidVacancy),
                });
              }}
              type="button"
            >
              Validar vacante
            </button>
            <button className="btn btn-violet" onClick={() => show("countCandidatesByStatus", countCandidatesByStatus(sampleCandidates))} type="button">Conteo por estado</button>
            <button className="btn btn-violet" onClick={() => show("calculateAverageSalary", calculateAverageSalary(sampleCandidates))} type="button">Salario promedio</button>
            <button className="btn btn-violet" onClick={() => show("findTopSkills", findTopSkills(sampleCandidates, 3))} type="button">Top 3 skills</button>
            <button className="btn btn-violet" onClick={() => show("calculateVacancyFillRate", calculateVacancyFillRate(sampleProcesses))} type="button">Vacancy fill rate</button>
          </div>
        </div>
      </article>

      <article className="panel output">
        <div className="panel-header">
          <h2>Salida JSON</h2>
          <span className="pill">{label}</span>
        </div>
        <pre>{result}</pre>
      </article>
    </section>
  );
}
