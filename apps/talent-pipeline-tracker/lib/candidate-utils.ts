import type { NoteOut, NotesResponse, RecordOut, RecordsResponse } from "@/types/candidates";
import { RECORDS_LIMIT } from "@/lib/candidate-constants";

export function recordsFromResponse(
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

export function notesFromResponse(response: NotesResponse): NoteOut[] {
  return Array.isArray(response) ? response : response.data;
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    received: "Recibida",
    in_progress: "En proceso",
    selected: "Seleccionada",
    discarded: "Descartada",
  };
  return map[status] ?? "Estado no definido";
}

export function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    pending: "Pendiente de revisión",
    review: "En revisión",
    personal_interview: "Entrevista personal",
    technical_interview: "Entrevista técnica",
    offer_presented: "Oferta presentada",
  };
  return map[stage] ?? "Etapa no definida";
}

export function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    in_progress: "bg-[#95A6FD] text-[#263888]",
    received: "bg-[#FFDBD1] text-[#872100]",
    selected: "bg-[#DEE1FF] text-[#0032C3]",
    discarded: "bg-[#FFDAD6] text-[#93000A]",
  };

  return map[status] ?? "bg-[#E2E1EF] text-[#434656]";
}

export function getInitials(fullName: string): string {
  return fullName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function formatAppliedDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "long",
  }).format(date);
}
