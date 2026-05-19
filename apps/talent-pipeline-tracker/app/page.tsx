"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getRecords } from "@/services/api";
import type { RecordOut, RecordsResponse } from "@/types/candidates";

function recordsFromResponse(response: RecordsResponse): RecordOut[] {
  return Array.isArray(response) ? response : response.data;
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    received: "Recibido",
    in_progress: "En proceso",
    selected: "Seleccionado",
    discarded: "Descartado",
  };
  return map[status] ?? status;
}

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    pending: "Pendiente",
    review: "Revisión",
    personal_interview: "Entrevista personal",
    technical_interview: "Entrevista técnica",
    offer_presented: "Oferta presentada",
  };
  return map[stage] ?? stage;
}

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    in_progress: "bg-[#95A6FD] text-[#263888]",
    received: "bg-[#FFDBD1] text-[#872100]",
    selected: "bg-[#DEE1FF] text-[#0032C3]",
    discarded: "bg-[#FFDAD6] text-[#93000A]",
  };

  return map[status] ?? "bg-[#E2E1EF] text-[#434656]";
}

function getInitials(fullName: string): string {
  return fullName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function ActionEyeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function KebabIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
      <circle cx="12" cy="5" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="12" cy="19" r="1.8" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function ChevronIcon({ direction }: { direction: "left" | "right" | "down" }) {
  const rotations: Record<string, string> = {
    left: "rotate-90",
    right: "-rotate-90",
    down: "rotate-0",
  };

  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-4 w-4 ${rotations[direction]}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function LoadingSkeleton() {
  return (
    <section className="overflow-hidden rounded-xl border border-[#C4C5D9] bg-white">
      <div className="grid grid-cols-5 gap-4 border-b border-[#C4C5D9] bg-[#F3F2FF] px-6 py-4">
        <div className="h-4 w-28 animate-pulse rounded bg-[#E2E1EF]" />
        <div className="h-4 w-24 animate-pulse rounded bg-[#E2E1EF]" />
        <div className="h-4 w-20 animate-pulse rounded bg-[#E2E1EF]" />
        <div className="h-4 w-20 animate-pulse rounded bg-[#E2E1EF]" />
        <div className="h-4 w-16 animate-pulse rounded bg-[#E2E1EF]" />
      </div>

      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="grid grid-cols-5 gap-4 border-b border-[#E2E1EF] px-6 py-5 last:border-b-0">
          <div className="h-4 w-52 animate-pulse rounded bg-[#E2E1EF]" />
          <div className="h-4 w-40 animate-pulse rounded bg-[#E2E1EF]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#E2E1EF]" />
          <div className="h-4 w-32 animate-pulse rounded bg-[#E2E1EF]" />
          <div className="h-4 w-12 animate-pulse rounded bg-[#E2E1EF]" />
        </div>
      ))}
    </section>
  );
}

export default function HomePage() {
  const [records, setRecords] = useState<RecordOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await getRecords();
      setRecords(recordsFromResponse(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar el listado de candidaturas.");
      setRecords([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRecords();
  }, [fetchRecords]);

  const hasRecords = useMemo(() => records.length > 0, [records]);

  return (
    <main className="mx-auto w-full max-w-[1120px] px-6 py-8">
      <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-[44px] font-semibold leading-[1.1] tracking-[-0.02em] text-[#191B25]">
            Gestión de Talentos
          </h1>
          <p className="mt-2 text-[22px] text-[#434656]">
            Administra y sigue el progreso de tus procesos de selección.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg bg-[#0037D0] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#1B4DFF]"
        >
          <PlusIcon />
          Nueva Candidatura
        </button>
      </header>

      <section className="mb-3 rounded-xl border border-[#C4C5D9] bg-white p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center">
          <div className="relative flex-1">
            <SearchIcon />
            <input
              placeholder="Buscar por nombre o puesto..."
              disabled
              readOnly
              className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] py-3 pl-11 pr-4 text-sm text-[#191B25] placeholder:text-[#747688]"
            />
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#747688]">
              <SearchIcon />
            </span>
          </div>

          <div className="flex w-full gap-3 md:w-auto">
            <button
              type="button"
              disabled
              className="inline-flex w-full items-center justify-between rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#434656] md:w-[146px]"
            >
              Estado: Todos
              <ChevronIcon direction="down" />
            </button>
            <button
              type="button"
              disabled
              className="inline-flex w-full items-center justify-between rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#434656] md:w-[146px]"
            >
              Etapa: Todas
              <ChevronIcon direction="down" />
            </button>
          </div>
        </div>
      </section>

      {isLoading && <LoadingSkeleton />}

      {!isLoading && error && (
        <section className="rounded-xl border border-rose-200 bg-rose-50 p-6">
          <p className="font-medium text-rose-900">No se pudo cargar el listado.</p>
          <p className="mt-1 text-sm text-rose-800">{error}</p>
          <button
            type="button"
            onClick={() => void fetchRecords()}
            className="mt-4 rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100"
          >
            Reintentar
          </button>
        </section>
      )}

      {!isLoading && !error && !hasRecords && (
        <section className="rounded-xl border border-[#C4C5D9] bg-white p-10 text-center">
          <h2 className="text-xl font-semibold text-[#191B25]">No hay candidaturas</h2>
          <p className="mt-2 text-[#434656]">Cuando existan registros en la API, aparecerán aquí.</p>
        </section>
      )}

      {!isLoading && !error && hasRecords && (
        <section className="overflow-hidden rounded-xl border border-[#C4C5D9] bg-white">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="bg-[#F3F2FF] text-[12px] uppercase tracking-[0.05em] text-[#747688]">
                <th className="px-5 py-4 font-semibold">Nombre</th>
                <th className="px-5 py-4 font-semibold">Puesto</th>
                <th className="px-5 py-4 font-semibold">Estado</th>
                <th className="px-5 py-4 font-semibold">Etapa</th>
                <th className="px-5 py-4 text-right font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {records.map((candidate) => (
                <tr key={candidate.id} className="border-t border-[#E2E1EF] transition-colors hover:bg-[#FBF8FF]">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#DEE1FF] text-[11px] font-bold text-[#2F4090]">
                        {getInitials(candidate.full_name)}
                      </div>
                      <div>
                        <p className="font-semibold text-[#191B25]">{candidate.full_name}</p>
                        <p className="text-[#747688]">{candidate.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-[#191B25]">{candidate.position}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex rounded-full px-3 py-1 text-[11px] font-bold uppercase ${statusBadgeClass(candidate.status)}`}
                    >
                      {statusLabel(candidate.status)}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-[#191B25]">{stageLabel(candidate.stage)}</td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2 text-[#0037D0]">
                      <button
                        type="button"
                        className="rounded-md p-1.5 text-[#0037D0] transition hover:bg-[#DEE1FF]"
                        aria-label="Ver"
                      >
                        <ActionEyeIcon />
                      </button>
                      <button
                        type="button"
                        className="rounded-md p-1.5 text-[#747688] transition hover:bg-[#F3F2FF]"
                        aria-label="Más acciones"
                      >
                        <KebabIcon />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <footer className="flex flex-col gap-3 border-t border-[#E2E1EF] bg-[#FBF8FF] px-5 py-3 md:flex-row md:items-center md:justify-between">
            <span className="text-[#747688]">Mostrando {records.length} de {records.length} candidatos</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded-md border border-[#C4C5D9] bg-white p-2 text-[#747688] hover:bg-[#F3F2FF]"
                aria-label="Anterior"
              >
                <ChevronIcon direction="left" />
              </button>
              <button type="button" className="rounded-md bg-[#0037D0] px-3 py-2 text-sm font-medium text-white">
                1
              </button>
              <button
                type="button"
                className="rounded-md border border-[#C4C5D9] bg-white px-3 py-2 text-sm text-[#434656] hover:bg-[#F3F2FF]"
              >
                2
              </button>
              <button
                type="button"
                className="rounded-md border border-[#C4C5D9] bg-white px-3 py-2 text-sm text-[#434656] hover:bg-[#F3F2FF]"
              >
                3
              </button>
              <button
                type="button"
                className="rounded-md border border-[#C4C5D9] bg-white p-2 text-[#747688] hover:bg-[#F3F2FF]"
                aria-label="Siguiente"
              >
                <ChevronIcon direction="right" />
              </button>
            </div>
          </footer>
        </section>
      )}
    </main>
  );
}
