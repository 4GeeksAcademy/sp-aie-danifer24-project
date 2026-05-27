import Link from "next/link";
import { useRef } from "react";
import { ChevronIcon } from "@/components/icons";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { getInitials, stageLabel, statusBadgeClass, statusLabel } from "@/lib/candidate-utils";
import type { RecordOut } from "@/types/candidates";

interface CandidatesTableProps {
  isLoading: boolean;
  error: string | null;
  hasRecords: boolean;
  records: RecordOut[];
  detailQuery: string;
  pageStart: number;
  pageEnd: number;
  totalRecords: number;
  currentPage: number;
  totalPages: number;
  pageNumbers: number[];
  onRetry: () => void;
  onPageChange: (page: number) => void;
}

export default function CandidatesTable({
  isLoading,
  error,
  hasRecords,
  records,
  detailQuery,
  pageStart,
  pageEnd,
  totalRecords,
  currentPage,
  totalPages,
  pageNumbers,
  onRetry,
  onPageChange,
}: CandidatesTableProps) {
  const listingRef = useRef<HTMLElement | null>(null);

  if (isLoading) return <LoadingSkeleton />;

  if (error) {
    return (
      <section className="rounded-xl border border-rose-200 bg-rose-50 p-6">
        <p className="font-medium text-rose-900">No se pudo cargar el listado.</p>
        <p className="mt-1 text-sm text-rose-800">{error}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100"
        >
          Reintentar
        </button>
      </section>
    );
  }

  if (!hasRecords) {
    return (
      <section className="rounded-xl border border-[#C4C5D9] bg-white p-10 text-center">
        <h2 className="text-xl font-semibold text-[#191B25]">No hay candidaturas</h2>
        <p className="mt-2 text-[#434656]">Cuando existan registros en la API, aparecerán aquí.</p>
      </section>
    );
  }

  return (
    <section ref={listingRef} className="overflow-hidden rounded-xl border border-[#C4C5D9] bg-white">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-[#F3F2FF] text-[12px] uppercase tracking-[0.05em] text-[#747688]">
            <th className="px-5 py-4 font-semibold">Nombre</th>
            <th className="px-5 py-4 font-semibold">Puesto</th>
            <th className="px-5 py-4 font-semibold">Estado</th>
            <th className="px-5 py-4 font-semibold">Etapa</th>
          </tr>
        </thead>
        <tbody>
          {records.map((candidate) => (
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
              onPageChange(currentPage - 1);
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
                onPageChange(pageNumber);
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
              onPageChange(currentPage + 1);
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
  );
}
