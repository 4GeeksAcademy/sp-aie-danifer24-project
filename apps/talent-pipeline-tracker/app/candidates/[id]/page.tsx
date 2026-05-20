"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createRecordNote, deleteRecordNote, getRecordById, getRecordNotes, patchRecord, replaceRecord } from "@/services/api";
import type { NoteOut, NotesResponse, RecordCreate, RecordOut } from "@/types/candidates";

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

interface EditFormData {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

type EditFormErrors = Partial<Record<keyof EditFormData, string>>;

function notesFromResponse(response: NotesResponse): NoteOut[] {
  return Array.isArray(response) ? response : response.data;
}

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
  const [notes, setNotes] = useState<NoteOut[]>([]);
  const [notesState, setNotesState] = useState<ControlState>("idle");
  const [notesError, setNotesError] = useState<string | null>(null);
  const [noteContent, setNoteContent] = useState("");
  const [createNoteState, setCreateNoteState] = useState<ControlState>("idle");
  const [createNoteError, setCreateNoteError] = useState<string | null>(null);
  const [deletingNoteId, setDeletingNoteId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteNoteState, setDeleteNoteState] = useState<ControlState>("idle");
  const [deleteNoteError, setDeleteNoteError] = useState<string | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editState, setEditState] = useState<ControlState>("idle");
  const [editError, setEditError] = useState<string | null>(null);
  const [editFormErrors, setEditFormErrors] = useState<EditFormErrors>({});
  const [editForm, setEditForm] = useState<EditFormData>({
    full_name: "",
    email: "",
    phone: "",
    position: "",
    linkedin_url: "",
    cv_url: "",
    experience_years: "",
  });

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

  const fetchNotes = useCallback(async () => {
    try {
      setNotesState("loading");
      setNotesError(null);
      const response = await getRecordNotes(candidateId);
      setNotes(notesFromResponse(response));
      setNotesState("success");
    } catch (err) {
      setNotes([]);
      setNotesState("error");
      setNotesError(err instanceof Error ? err.message : "No se pudieron cargar las notas.");
    }
  }, [candidateId]);

  useEffect(() => {
    void fetchNotes();
  }, [fetchNotes]);

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

  const handleCreateNote = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const trimmedContent = noteContent.trim();

      if (!trimmedContent) {
        setCreateNoteState("error");
        setCreateNoteError("Completa el contenido para guardar la nota.");
        return;
      }

      try {
        setCreateNoteState("loading");
        setCreateNoteError(null);
        const created = await createRecordNote(candidateId, {
          title: trimmedContent.slice(0, 50),
          content: trimmedContent,
        });
        setNotes((current) => [created, ...current]);
        setNoteContent("");
        setCreateNoteState("success");
      } catch (err) {
        setCreateNoteState("error");
        setCreateNoteError(err instanceof Error ? err.message : "No se pudo crear la nota.");
      }
    },
    [candidateId, noteContent],
  );

  const handleDeleteNote = useCallback(
    async (noteId: string) => {
      try {
        setDeletingNoteId(noteId);
        setDeleteNoteState("loading");
        setDeleteNoteError(null);
        await deleteRecordNote(candidateId, noteId);
        setNotes((current) => current.filter((note) => note.id !== noteId));
        setConfirmDeleteId(null);
        setDeleteNoteState("success");
      } catch (err) {
        setDeleteNoteState("error");
        setDeleteNoteError(err instanceof Error ? err.message : "No se pudo eliminar la nota.");
      } finally {
        setDeletingNoteId(null);
      }
    },
    [candidateId],
  );

  const validateEditForm = useCallback((values: EditFormData): EditFormErrors => {
    const nextErrors: EditFormErrors = {};

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

  const openEditModal = useCallback(() => {
    if (!record) return;

    setEditForm({
      full_name: record.full_name,
      email: record.email,
      phone: record.phone,
      position: record.position,
      linkedin_url: record.linkedin_url ?? "",
      cv_url: record.cv_url ?? "",
      experience_years: String(record.experience_years),
    });
    setEditFormErrors({});
    setEditError(null);
    setEditState("idle");
    setIsEditModalOpen(true);
  }, [record]);

  const handleEditCandidate = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const validationErrors = validateEditForm(editForm);
      setEditFormErrors(validationErrors);

      if (Object.keys(validationErrors).length > 0) {
        setEditState("error");
        setEditError("Revisa los campos obligatorios.");
        return;
      }

      const payload: RecordCreate = {
        full_name: editForm.full_name.trim(),
        email: editForm.email.trim(),
        phone: editForm.phone.trim(),
        position: editForm.position.trim(),
        experience_years: Number(editForm.experience_years),
        linkedin_url: editForm.linkedin_url.trim() || undefined,
        cv_url: editForm.cv_url.trim() || undefined,
      };

      try {
        setEditState("loading");
        setEditError(null);
        const updated = await replaceRecord(candidateId, payload);
        setRecord(updated);
        setEditState("success");
      } catch (err) {
        setEditState("error");
        setEditError(err instanceof Error ? err.message : "No se pudo actualizar la candidatura.");
      }
    },
    [candidateId, editForm, validateEditForm],
  );

  return (
    <main className="mx-auto w-full max-w-[1120px] px-6 py-8">
      <div className="mb-6 flex items-center justify-between gap-3">
        <Link href={listHref} className="inline-flex items-center text-sm font-medium text-[#0037D0] hover:underline">
          Volver al listado
        </Link>
        {!isLoading && !error && record && (
          <button
            type="button"
            onClick={openEditModal}
            className="rounded-lg bg-[#0037D0] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1B4DFF]"
          >
            Editar candidatura
          </button>
        )}
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
        <div className="grid gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] md:items-start">
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

          <section className="rounded-xl border border-[#C4C5D9] bg-white p-6">
            <header className="mb-4">
              <h2 className="text-xl font-semibold text-[#191B25]">Notas internas</h2>
            </header>

            <form onSubmit={handleCreateNote} className="mb-5 rounded-lg border border-[#E2E1EF] p-4">
              <div className="grid gap-3">
                <textarea
                  placeholder="Escribe una nota interna..."
                  value={noteContent}
                  onChange={(event) => setNoteContent(event.target.value)}
                  disabled={createNoteState === "loading"}
                  rows={4}
                  className="w-full resize-y rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25] placeholder:text-[#747688]"
                />
                <div>
                  <button
                    type="submit"
                    disabled={createNoteState === "loading"}
                    className="rounded-lg bg-[#0037D0] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {createNoteState === "loading" ? "Guardando..." : "Añadir nota"}
                  </button>
                </div>
              </div>
              {createNoteState === "success" && <p className="mt-3 text-xs text-emerald-700">Nota creada.</p>}
              {createNoteState === "error" && <p className="mt-3 text-xs text-rose-700">{createNoteError ?? "No se pudo crear la nota."}</p>}
            </form>

            {notesState === "loading" && <p className="text-sm text-[#434656]">Cargando notas...</p>}
            {notesState === "error" && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
                <p className="text-sm font-medium text-rose-900">No se pudieron cargar las notas.</p>
                <p className="mt-1 text-xs text-rose-800">{notesError}</p>
                <button
                  type="button"
                  onClick={() => void fetchNotes()}
                  className="mt-3 rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-800 hover:bg-rose-100"
                >
                  Reintentar
                </button>
              </div>
            )}

            {notesState === "success" && notes.length === 0 && (
              <p className="text-sm text-[#434656]">Aun no hay notas para esta candidatura.</p>
            )}

            {notesState === "success" && notes.length > 0 && (
              <ul className="space-y-3">
                {notes.map((note) => {
                  const isConfirmingDelete = confirmDeleteId === note.id;
                  const isDeletingThisNote = deletingNoteId === note.id;

                  return (
                    <li key={note.id} className="rounded-lg border border-[#E2E1EF] bg-[#F8F7FF] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-[#191B25]">{note.title}</h3>
                          <p className="mt-1 text-sm text-[#434656]">{note.content}</p>
                        </div>
                        {!isConfirmingDelete && (
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(note.id)}
                            className="rounded-lg border border-[#C4C5D9] px-3 py-1.5 text-xs font-medium text-[#434656] hover:bg-[#F3F2FF]"
                          >
                            Eliminar
                          </button>
                        )}
                        {isConfirmingDelete && (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => void handleDeleteNote(note.id)}
                              disabled={isDeletingThisNote}
                              className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-70"
                            >
                              {isDeletingThisNote ? "Eliminando..." : "Confirmar"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmDeleteId(null)}
                              disabled={isDeletingThisNote}
                              className="rounded-lg border border-[#C4C5D9] px-3 py-1.5 text-xs font-medium text-[#434656] hover:bg-[#F3F2FF] disabled:cursor-not-allowed disabled:opacity-70"
                            >
                              Cancelar
                            </button>
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            {deleteNoteState === "success" && <p className="mt-3 text-xs text-emerald-700">Nota eliminada.</p>}
            {deleteNoteState === "error" && (
              <p className="mt-3 text-xs text-rose-700">{deleteNoteError ?? "No se pudo eliminar la nota."}</p>
            )}
          </section>
        </div>
      )}

      {isEditModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#191B25]/45 px-4"
          onClick={() => setIsEditModalOpen(false)}
        >
          <div
            className="w-full max-w-2xl rounded-xl border border-[#C4C5D9] bg-white p-6 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-2xl font-semibold text-[#191B25]">Editar candidatura</h2>
                <p className="mt-1 text-sm text-[#434656]">Actualiza los datos y guarda los cambios.</p>
              </div>
            </div>

            <form onSubmit={handleEditCandidate} className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Nombre completo *</span>
                  <input
                    value={editForm.full_name}
                    onChange={(event) => {
                      setEditForm((prev) => ({ ...prev, full_name: event.target.value }));
                      setEditFormErrors((prev) => ({ ...prev, full_name: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {editFormErrors.full_name && <span className="mt-1 block text-xs text-rose-700">{editFormErrors.full_name}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Email *</span>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={(event) => {
                      setEditForm((prev) => ({ ...prev, email: event.target.value }));
                      setEditFormErrors((prev) => ({ ...prev, email: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {editFormErrors.email && <span className="mt-1 block text-xs text-rose-700">{editFormErrors.email}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Teléfono *</span>
                  <input
                    value={editForm.phone}
                    onChange={(event) => {
                      setEditForm((prev) => ({ ...prev, phone: event.target.value }));
                      setEditFormErrors((prev) => ({ ...prev, phone: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {editFormErrors.phone && <span className="mt-1 block text-xs text-rose-700">{editFormErrors.phone}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Puesto *</span>
                  <input
                    value={editForm.position}
                    onChange={(event) => {
                      setEditForm((prev) => ({ ...prev, position: event.target.value }));
                      setEditFormErrors((prev) => ({ ...prev, position: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {editFormErrors.position && <span className="mt-1 block text-xs text-rose-700">{editFormErrors.position}</span>}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">Años de experiencia *</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={editForm.experience_years}
                    onChange={(event) => {
                      setEditForm((prev) => ({ ...prev, experience_years: event.target.value }));
                      setEditFormErrors((prev) => ({ ...prev, experience_years: undefined }));
                    }}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                  {editFormErrors.experience_years && (
                    <span className="mt-1 block text-xs text-rose-700">{editFormErrors.experience_years}</span>
                  )}
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">LinkedIn</span>
                  <input
                    type="url"
                    value={editForm.linkedin_url}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, linkedin_url: event.target.value }))}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                </label>

                <label className="block md:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-[#191B25]">URL CV</span>
                  <input
                    type="url"
                    value={editForm.cv_url}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, cv_url: event.target.value }))}
                    className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
                  />
                </label>
              </div>

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  disabled={editState === "loading"}
                  className="rounded-lg border border-[#C4C5D9] px-4 py-2 text-sm font-medium text-[#434656] hover:bg-[#F3F2FF] disabled:opacity-70"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={editState === "loading"}
                  className="rounded-lg bg-[#0037D0] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1B4DFF] disabled:opacity-70"
                >
                  {editState === "loading" ? "Guardando..." : "Guardar cambios"}
                </button>
              </div>

              {editState === "success" && <p className="text-sm text-emerald-700">Candidatura actualizada correctamente.</p>}
              {editState === "error" && editError && <p className="text-sm text-rose-700">{editError}</p>}
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
