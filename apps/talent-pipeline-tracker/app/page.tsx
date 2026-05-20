"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createRecord, getRecords } from "@/services/api";
import type { RecordCreate, RecordOut, RecordsResponse } from "@/types/candidates";

const RECORDS_LIMIT = 20;

type SubmitState = "idle" | "loading" | "success" | "error";

interface CreateFormData {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

type CreateFormErrors = Partial<Record<keyof CreateFormData, string>>;

function recordsFromResponse(
  response: RecordsResponse,
  fallbackPage: number,
): { records: RecordOut[]; total: number; page: number; limit: number } {
  if (Array.isArray(response)) {
    return {
      records: response,
      total: response.length,
      page: fallbackPage,
      limit: RECORDS_LIMIT,
    };
  }

  return {
    records: response.data,
    total: typeof response.total === "number" ? response.total : response.data.length,
    page: typeof response.page === "number" ? response.page : fallbackPage,
    limit: typeof response.limit === "number" ? response.limit : RECORDS_LIMIT,
  };
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

const STATUS_OPTIONS = [
  { value: "all", label: "Estado: Todos" },
  { value: "received", label: "Recibido" },
  { value: "in_progress", label: "En proceso" },
  { value: "selected", label: "Seleccionado" },
  { value: "discarded", label: "Descartado" },
];

const STAGE_OPTIONS = [
  { value: "all", label: "Etapa: Todas" },
  { value: "pending", label: "Pendiente" },
  { value: "review", label: "Revisión" },
  { value: "personal_interview", label: "Entrevista personal" },
  { value: "technical_interview", label: "Entrevista técnica" },
  { value: "offer_presented", label: "Oferta presentada" },
];

function getInitials(fullName: string): string {
  return fullName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
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
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const searchParamsRef = useRef(searchParams);
  const listingRef = useRef<HTMLElement | null>(null);
  const detailQuery = searchParams.toString();

  const [records, setRecords] = useState<RecordOut[]>([]);
  const [totalRecords, setTotalRecords] = useState(0);
  const [pageLimit, setPageLimit] = useState(RECORDS_LIMIT);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const statusFilter = searchParams.get("status") ?? "all";
  const stageFilter = searchParams.get("stage") ?? "all";
  const pageFromQuery = Number(searchParams.get("page") ?? "1");
  const currentPage = Number.isFinite(pageFromQuery) && pageFromQuery > 0 ? pageFromQuery : 1;
  const searchValue = searchParams.get("search") ?? "";
  const [inputValue, setInputValue] = useState(searchValue);
  const [searchQuery, setSearchQuery] = useState(searchValue);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createState, setCreateState] = useState<SubmitState>("idle");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createFormErrors, setCreateFormErrors] = useState<CreateFormErrors>({});
  const [createForm, setCreateForm] = useState<CreateFormData>({
    full_name: "",
    email: "",
    phone: "",
    position: "",
    linkedin_url: "",
    cv_url: "",
    experience_years: "",
  });

  const validateCreateForm = useCallback((values: CreateFormData): CreateFormErrors => {
    const nextErrors: CreateFormErrors = {};

    if (!values.full_name.trim()) nextErrors.full_name = "El nombre es obligatorio.";

    const email = values.email.trim();
    if (!email) nextErrors.email = "El email es obligatorio.";
    else if (!/^\S+@\S+\.\S+$/.test(email)) nextErrors.email = "El email no es válido.";

    if (!values.phone.trim()) nextErrors.phone = "El teléfono es obligatorio.";
    if (!values.position.trim()) nextErrors.position = "El puesto es obligatorio.";

    if (!values.experience_years.trim()) {
      nextErrors.experience_years = "Los años de experiencia son obligatorios.";
    } else {
      const years = Number(values.experience_years);
      if (!Number.isFinite(years) || years < 0) {
        nextErrors.experience_years = "Introduce un número válido (0 o más).";
      }
    }

    return nextErrors;
  }, []);

  const resetCreateForm = useCallback(() => {
    setCreateForm({
      full_name: "",
      email: "",
      phone: "",
      position: "",
      linkedin_url: "",
      cv_url: "",
      experience_years: "",
    });
    setCreateFormErrors({});
    setCreateError(null);
    setCreateState("idle");
  }, []);

  const fetchRecords = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await getRecords({
        page: currentPage,
        limit: RECORDS_LIMIT,
        status: statusFilter !== "all" ? statusFilter : undefined,
        stage: stageFilter !== "all" ? stageFilter : undefined,
        search: searchValue.trim() ? searchValue : undefined,
      });
      const parsed = recordsFromResponse(response, currentPage);
      setRecords(parsed.records);
      setTotalRecords(parsed.total);
      setPageLimit(parsed.limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar el listado de candidaturas.");
      setRecords([]);
      setTotalRecords(0);
    } finally {
      setIsLoading(false);
    }
  }, [currentPage, searchValue, stageFilter, statusFilter]);

  useEffect(() => {
    void fetchRecords();
  }, [fetchRecords]);

  const handleCreateCandidate = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const validationErrors = validateCreateForm(createForm);
      setCreateFormErrors(validationErrors);

      if (Object.keys(validationErrors).length > 0) {
        setCreateState("error");
        setCreateError("Revisa los campos obligatorios.");
        return;
      }

      const payload: RecordCreate = {
        full_name: createForm.full_name.trim(),
        email: createForm.email.trim(),
        phone: createForm.phone.trim(),
        position: createForm.position.trim(),
        experience_years: Number(createForm.experience_years),
        linkedin_url: createForm.linkedin_url.trim() || undefined,
        cv_url: createForm.cv_url.trim() || undefined,
      };

      try {
        setCreateState("loading");
        setCreateError(null);
        await createRecord(payload);
        setCreateState("success");
        await fetchRecords();
        setIsCreateModalOpen(false);
        resetCreateForm();
        router.replace("/", { scroll: false });
      } catch (err) {
        setCreateState("error");
        setCreateError(err instanceof Error ? err.message : "No se pudo crear la candidatura.");
      }
    },
    [createForm, fetchRecords, resetCreateForm, router, validateCreateForm],
  );

  useEffect(() => {
    searchParamsRef.current = searchParams;
    const nextSearch = searchParams.get("search") ?? "";
    setInputValue(nextSearch);
    setSearchQuery(nextSearch);
  }, [searchParams]);

  const filteredRecords = useMemo(() => {
    return records.filter((candidate) => {
      const matchesStatus = statusFilter === "all" || candidate.status === statusFilter;
      const matchesStage = stageFilter === "all" || candidate.stage === stageFilter;

      const query = searchQuery.trim().toLowerCase();
      const matchesSearch =
        query.length === 0 ||
        candidate.full_name.toLowerCase().includes(query) ||
        candidate.email.toLowerCase().includes(query);

      return matchesStatus && matchesStage && matchesSearch;
    });
  }, [records, searchQuery, stageFilter, statusFilter]);

  const hasRecords = useMemo(() => filteredRecords.length > 0, [filteredRecords]);
  const totalPages = useMemo(() => {
    if (!totalRecords) return 1;
    return Math.ceil(totalRecords / pageLimit);
  }, [pageLimit, totalRecords]);
  const pageNumbers = useMemo(() => {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }, [totalPages]);
  const pageStart = useMemo(() => {
    if (totalRecords === 0 || filteredRecords.length === 0) return 0;
    return (currentPage - 1) * pageLimit + 1;
  }, [currentPage, filteredRecords.length, pageLimit, totalRecords]);
  const pageEnd = useMemo(() => {
    if (totalRecords === 0 || filteredRecords.length === 0) return 0;
    return Math.min((currentPage - 1) * pageLimit + filteredRecords.length, totalRecords);
  }, [currentPage, filteredRecords.length, pageLimit, totalRecords]);

  const updateParams = useCallback(
    (next: { status?: string; stage?: string; search?: string; page?: number }) => {
      const params = new URLSearchParams(searchParamsRef.current.toString());

      if (next.status !== undefined) {
        if (!next.status || next.status === "all") params.delete("status");
        else params.set("status", next.status);
      }

      if (next.stage !== undefined) {
        if (!next.stage || next.stage === "all") params.delete("stage");
        else params.set("stage", next.stage);
      }

      if (next.search !== undefined) {
        if (!next.search.trim()) params.delete("search");
        else params.set("search", next.search);
      }

      if (next.page !== undefined) {
        if (!next.page || next.page <= 1) params.delete("page");
        else params.set("page", String(next.page));
      }

      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchQuery(inputValue);
      updateParams({ search: inputValue, page: 1 });
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [inputValue, updateParams]);

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
          onClick={() => {
            resetCreateForm();
            setIsCreateModalOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-[#0037D0] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#1B4DFF]"
        >
          <PlusIcon />
          Nueva Candidatura
        </button>
      </header>

      <section className="mb-3 rounded-xl border border-[#C4C5D9] bg-white p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center">
          <div className="relative flex-1">
            <input
              placeholder="Buscar por nombre o puesto..."
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] py-3 pl-11 pr-4 text-sm text-[#191B25] placeholder:text-[#747688]"
            />
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#747688]">
              <SearchIcon />
            </span>
          </div>

          <div className="flex w-full gap-3 md:w-auto">
            <div className="relative w-full md:w-[146px]"
            >
              <select
                value={statusFilter}
                onChange={(event) => updateParams({ status: event.target.value, page: 1 })}
                className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#434656]">
                <ChevronIcon direction="down" />
              </span>
            </div>
            <div className="relative w-full md:w-[146px]"
            >
              <select
                value={stageFilter}
                onChange={(event) => updateParams({ stage: event.target.value, page: 1 })}
                className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
              >
                {STAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#434656]">
                <ChevronIcon direction="down" />
              </span>
            </div>
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
        <section ref={listingRef} className="overflow-hidden rounded-xl border border-[#C4C5D9] bg-white">
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
              {filteredRecords.map((candidate) => (
                <tr key={candidate.id} className="relative border-t border-[#E2E1EF] transition-colors hover:bg-[#FBF8FF]">
                  <td className="px-5 py-4">
                    <Link
                      href={detailQuery ? `/candidates/${candidate.id}?${detailQuery}` : `/candidates/${candidate.id}`}
                      className="absolute inset-0 z-10"
                      aria-label={`Ver detalle de ${candidate.full_name}`}
                    />
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
                      className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-bold uppercase ${statusBadgeClass(candidate.status)}`}
                    >
                      {statusLabel(candidate.status)}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-[#191B25]">{stageLabel(candidate.stage)}</td>
                  <td className="px-5 py-4">
                    <div className="relative z-20 flex justify-end gap-2 text-[#0037D0]">
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
            <span className="text-[#747688]">Mostrando {pageStart}-{pageEnd} de {totalRecords} resultados</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  updateParams({ page: currentPage - 1 });
                  listingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                disabled={currentPage <= 1}
                className="rounded-md border border-[#C4C5D9] bg-white p-2 text-[#747688] hover:bg-[#F3F2FF] disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Anterior"
              >
                <ChevronIcon direction="left" />
              </button>
              {pageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  type="button"
                  onClick={() => {
                    updateParams({ page: pageNumber });
                    listingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                  className={
                    pageNumber === currentPage
                      ? "rounded-md bg-[#0037D0] px-3 py-2 text-sm font-medium text-white"
                      : "rounded-md border border-[#C4C5D9] bg-white px-3 py-2 text-sm text-[#434656] hover:bg-[#F3F2FF]"
                  }
                  aria-label={`Página ${pageNumber}`}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  updateParams({ page: currentPage + 1 });
                  listingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                disabled={currentPage >= totalPages}
                className="rounded-md border border-[#C4C5D9] bg-white p-2 text-[#747688] hover:bg-[#F3F2FF] disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Siguiente"
              >
                <ChevronIcon direction="right" />
              </button>
            </div>
          </footer>
        </section>
      )}

      {isCreateModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#191B25]/45 px-4"
          onClick={() => {
            setIsCreateModalOpen(false);
            resetCreateForm();
          }}
        >
          <div
            className="w-full max-w-2xl rounded-xl border border-[#C4C5D9] bg-white p-6 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-2xl font-semibold text-[#191B25]">Nueva candidatura</h2>
                <p className="mt-1 text-sm text-[#434656]">Completa los datos obligatorios para registrar la candidatura.</p>
              </div>
            </div>

            <form onSubmit={handleCreateCandidate} className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Nombre completo *</span>
                  <input
                    value={createForm.full_name}
                    onChange={(event) => {
                      setCreateForm((prev) => ({ ...prev, full_name: event.target.value }));
                      setCreateFormErrors((prev) => ({ ...prev, full_name: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {createFormErrors.full_name && <span className="mt-1 block text-xs text-rose-700">{createFormErrors.full_name}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Email *</span>
                  <input
                    type="email"
                    value={createForm.email}
                    onChange={(event) => {
                      setCreateForm((prev) => ({ ...prev, email: event.target.value }));
                      setCreateFormErrors((prev) => ({ ...prev, email: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {createFormErrors.email && <span className="mt-1 block text-xs text-rose-700">{createFormErrors.email}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Teléfono *</span>
                  <input
                    value={createForm.phone}
                    onChange={(event) => {
                      setCreateForm((prev) => ({ ...prev, phone: event.target.value }));
                      setCreateFormErrors((prev) => ({ ...prev, phone: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {createFormErrors.phone && <span className="mt-1 block text-xs text-rose-700">{createFormErrors.phone}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Puesto *</span>
                  <input
                    value={createForm.position}
                    onChange={(event) => {
                      setCreateForm((prev) => ({ ...prev, position: event.target.value }));
                      setCreateFormErrors((prev) => ({ ...prev, position: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {createFormErrors.position && <span className="mt-1 block text-xs text-rose-700">{createFormErrors.position}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Años de experiencia *</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={createForm.experience_years}
                    onChange={(event) => {
                      setCreateForm((prev) => ({ ...prev, experience_years: event.target.value }));
                      setCreateFormErrors((prev) => ({ ...prev, experience_years: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {createFormErrors.experience_years && (
                    <span className="mt-1 block text-xs text-rose-700">{createFormErrors.experience_years}</span>
                  )}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">LinkedIn</span>
                  <input
                    type="url"
                    value={createForm.linkedin_url}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, linkedin_url: event.target.value }))}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                </label>

                <label className="block md:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">URL CV</span>
                  <input
                    type="url"
                    value={createForm.cv_url}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, cv_url: event.target.value }))}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                </label>
              </div>

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setIsCreateModalOpen(false);
                    resetCreateForm();
                  }}
                  disabled={createState === "loading"}
                  className="rounded-lg border border-[#C4C5D9] px-4 py-2 text-sm font-medium text-[#434656] hover:bg-[#F3F2FF] disabled:opacity-70"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={createState === "loading"}
                  className="rounded-lg bg-[#0037D0] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1B4DFF] disabled:opacity-70"
                >
                  {createState === "loading" ? "Guardando..." : "Guardar candidatura"}
                </button>
              </div>

              {createState === "success" && <p className="text-sm text-emerald-700">Candidatura creada correctamente.</p>}
              {createState === "error" && createError && <p className="text-sm text-rose-700">{createError}</p>}
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
