"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getRecordById, patchRecord } from "@/services/api";
import type { RecordOut } from "@/types/candidates";

const STATUS_OPTIONS = [
  { value: "received", label: "Recibido" },
  { value: "in_progress", label: "En proceso" },
  { value: "selected", label: "Seleccionado" },
  { value: "discarded", label: "Descartado" },
];

const STAGE_OPTIONS = [
  { value: "pending", label: "Pendiente" },
  { value: "review", label: "Revisión" },
  { value: "personal_interview", label: "Entrevista personal" },
  { value: "technical_interview", label: "Entrevista técnica" },
  { value: "offer_presented", label: "Oferta presentada" },
];

type ControlState = "idle" | "loading" | "success" | "error";

function ChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
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

function formatAppliedDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "long",
  }).format(date);
}

function DetailsSkeleton() {
  return (
    <section className="space-y-5">
      <div className="h-6 w-40 animate-pulse rounded bg-[#E2E1EF]" />
      <div className="rounded-xl border border-[#C4C5D9] bg-white p-6">
        <div className="mb-5 h-8 w-72 animate-pulse rounded bg-[#E2E1EF]" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 10 }).map((_, index) => (
            <div key={index} className="rounded-lg border border-[#E2E1EF] p-4">
              <div className="h-3 w-24 animate-pulse rounded bg-[#E2E1EF]" />
              <div className="mt-3 h-4 w-40 animate-pulse rounded bg-[#E2E1EF]" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();

  const candidateId = params.id;
  const [record, setRecord] = useState<RecordOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusState, setStatusState] = useState<ControlState>("idle");
  const [statusError, setStatusError] = useState<string | null>(null);
  const [stageState, setStageState] = useState<ControlState>("idle");
  const [stageError, setStageError] = useState<string | null>(null);

  const listHref = useMemo(() => {
    const query = searchParams.toString();
    return query ? `/?${query}` : "/";
  }, [searchParams]);

  const fetchCandidate = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await getRecordById(candidateId);
      setRecord(result);
    } catch (err) {
      setRecord(null);
      setError(err instanceof Error ? err.message : "No se pudo cargar la candidatura.");
    } finally {
      setIsLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    void fetchCandidate();
  }, [fetchCandidate]);

  const handleStatusChange = useCallback(
    async (nextStatus: string) => {
      if (!record || nextStatus === record.status) {
        return;
      }

      try {
        setStatusState("loading");
        setStatusError(null);
        const updated = await patchRecord(candidateId, { status: nextStatus });
        setRecord(updated);
        setStatusState("success");
      } catch (err) {
        setStatusState("error");
        setStatusError(err instanceof Error ? err.message : "No se pudo actualizar el estado.");
      }
    },
    [candidateId, record],
  );

  const handleStageChange = useCallback(
    async (nextStage: string) => {
      if (!record || nextStage === record.stage) {
        return;
      }

      try {
        setStageState("loading");
        setStageError(null);
        const updated = await patchRecord(candidateId, { stage: nextStage });
        setRecord(updated);
        setStageState("success");
      } catch (err) {
        setStageState("error");
        setStageError(err instanceof Error ? err.message : "No se pudo actualizar la etapa.");
      }
    },
    [candidateId, record],
  );

  return (
    <main className="mx-auto w-full max-w-[1120px] px-6 py-8">
      <div className="mb-6">
        <Link href={listHref} className="inline-flex items-center text-sm font-medium text-[#0037D0] hover:underline">
          Volver al listado
        </Link>
      </div>

      {isLoading && <DetailsSkeleton />}

      {!isLoading && error && (
        <section className="rounded-xl border border-rose-200 bg-rose-50 p-6">
          <p className="font-medium text-rose-900">No se pudo cargar el detalle de la candidatura.</p>
          <p className="mt-1 text-sm text-rose-800">{error}</p>
          <button
            type="button"
            onClick={() => void fetchCandidate()}
            className="mt-4 rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100"
          >
            Reintentar
          </button>
        </section>
      )}

      {!isLoading && !error && record && (
        <section className="rounded-xl border border-[#C4C5D9] bg-white p-6">
          <header className="mb-6">
            <h1 className="text-3xl font-semibold tracking-[-0.02em] text-[#191B25]">{record.full_name}</h1>
            <p className="mt-1 text-[#434656]">{record.position}</p>
          </header>

          <dl className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Email</dt>
              <dd className="mt-2 text-[#191B25]">{record.email}</dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Teléfono</dt>
              <dd className="mt-2 text-[#191B25]">{record.phone}</dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Puesto</dt>
              <dd className="mt-2 text-[#191B25]">{record.position}</dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">LinkedIn</dt>
              <dd className="mt-2 text-[#191B25]">
                {record.linkedin_url ? (
                  <a
                    href={record.linkedin_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-[#0037D0] hover:underline"
                  >
                    Ver perfil
                  </a>
                ) : (
                  "No disponible"
                )}
              </dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">CV</dt>
              <dd className="mt-2 text-[#191B25]">
                {record.cv_url ? (
                  <a href={record.cv_url} target="_blank" rel="noreferrer" className="font-medium text-[#0037D0] hover:underline">
                    Abrir CV
                  </a>
                ) : (
                  "No disponible"
                )}
              </dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Años de experiencia</dt>
              <dd className="mt-2 text-[#191B25]">{record.experience_years}</dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Estado</dt>
              <dd className="mt-2 text-[#191B25]">
                <div className="relative">
                  <select
                    value={record.status}
                    onChange={(event) => void handleStatusChange(event.target.value)}
                    disabled={statusState === "loading"}
                    className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
                  >
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#434656]">
                    <ChevronIcon />
                  </span>
                </div>
                {statusState === "loading" && <p className="mt-2 text-xs text-[#434656]">Actualizando estado...</p>}
                {statusState === "success" && <p className="mt-2 text-xs text-emerald-700">Estado actualizado.</p>}
                {statusState === "error" && <p className="mt-2 text-xs text-rose-700">{statusError ?? "No se pudo actualizar el estado."}</p>}
              </dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Etapa</dt>
              <dd className="mt-2 text-[#191B25]">
                <div className="relative">
                  <select
                    value={record.stage}
                    onChange={(event) => void handleStageChange(event.target.value)}
                    disabled={stageState === "loading"}
                    className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
                  >
                    {STAGE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#434656]">
                    <ChevronIcon />
                  </span>
                </div>
                {stageState === "loading" && <p className="mt-2 text-xs text-[#434656]">Actualizando etapa...</p>}
                {stageState === "success" && <p className="mt-2 text-xs text-emerald-700">Etapa actualizada.</p>}
                {stageState === "error" && <p className="mt-2 text-xs text-rose-700">{stageError ?? "No se pudo actualizar la etapa."}</p>}
              </dd>
            </div>

            <div className="rounded-lg border border-[#E2E1EF] p-4 md:col-span-2">
              <dt className="text-xs font-semibold uppercase tracking-[0.04em] text-[#747688]">Fecha de aplicación</dt>
              <dd className="mt-2 text-[#191B25]">{formatAppliedDate(record.applied_at)}</dd>
            </div>
          </dl>
        </section>
      )}
    </main>
  );
}
