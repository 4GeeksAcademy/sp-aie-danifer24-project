import type { CreateFormData, CreateFormErrors, SubmitState } from "@/types/forms";

interface CreateCandidateModalProps {
  isOpen: boolean;
  onClose: () => void;
  formData: CreateFormData;
  formErrors: CreateFormErrors;
  submitState: SubmitState;
  submitError: string | null;
  onFieldChange: (field: keyof CreateFormData, value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
}

export default function CreateCandidateModal({
  isOpen,
  onClose,
  formData,
  formErrors,
  submitState,
  submitError,
  onFieldChange,
  onSubmit,
}: CreateCandidateModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#191B25]/45 px-4" onClick={onClose}>
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

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">Nombre completo *</span>
              <input
                value={formData.full_name}
                onChange={(event) => onFieldChange("full_name", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
              {formErrors.full_name && <span className="mt-1 block text-xs text-rose-700">{formErrors.full_name}</span>}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">Email *</span>
              <input
                type="email"
                value={formData.email}
                onChange={(event) => onFieldChange("email", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
              {formErrors.email && <span className="mt-1 block text-xs text-rose-700">{formErrors.email}</span>}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">Teléfono *</span>
              <input
                value={formData.phone}
                onChange={(event) => onFieldChange("phone", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
              {formErrors.phone && <span className="mt-1 block text-xs text-rose-700">{formErrors.phone}</span>}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">Puesto *</span>
              <input
                value={formData.position}
                onChange={(event) => onFieldChange("position", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
              {formErrors.position && <span className="mt-1 block text-xs text-rose-700">{formErrors.position}</span>}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">Años de experiencia *</span>
              <input
                type="number"
                min="0"
                step="1"
                value={formData.experience_years}
                onChange={(event) => onFieldChange("experience_years", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
              {formErrors.experience_years && <span className="mt-1 block text-xs text-rose-700">{formErrors.experience_years}</span>}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">LinkedIn</span>
              <input
                type="url"
                value={formData.linkedin_url}
                onChange={(event) => onFieldChange("linkedin_url", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
            </label>

            <label className="block md:col-span-2">
              <span className="mb-1 block text-sm font-medium text-[#191B25]">URL CV</span>
              <input
                type="url"
                value={formData.cv_url}
                onChange={(event) => onFieldChange("cv_url", event.target.value)}
                className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 text-sm text-[#191B25]"
              />
            </label>
          </div>

          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={submitState === "loading"}
              className="rounded-lg border border-[#C4C5D9] px-4 py-2 text-sm font-medium text-[#434656] hover:bg-[#F3F2FF] disabled:opacity-70"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submitState === "loading"}
              className="rounded-lg bg-[#0037D0] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1B4DFF] disabled:opacity-70"
            >
              {submitState === "loading" ? "Guardando..." : "Guardar candidatura"}
            </button>
          </div>

          {submitState === "success" && <p className="text-sm text-emerald-700">Candidatura creada correctamente.</p>}
          {submitState === "error" && submitError && <p className="text-sm text-rose-700">{submitError}</p>}
        </form>
      </div>
    </div>
  );
}
