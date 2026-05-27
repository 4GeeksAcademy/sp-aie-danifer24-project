import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { createRecord } from "@/services/api";
import { validateCreateCandidateForm } from "@/lib/validation";
import type { RecordCreate } from "@/types/candidates";
import type { CreateFormData, CreateFormErrors, SubmitState } from "@/types/forms";

interface UseCreateCandidateFormOptions {
  onCreated: () => Promise<void>;
}

const EMPTY_FORM: CreateFormData = {
  full_name: "",
  email: "",
  phone: "",
  position: "",
  linkedin_url: "",
  cv_url: "",
  experience_years: "",
};

export function useCreateCandidateForm({ onCreated }: UseCreateCandidateFormOptions) {
  const router = useRouter();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createState, setCreateState] = useState<SubmitState>("idle");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createFormErrors, setCreateFormErrors] = useState<CreateFormErrors>({});
  const [createForm, setCreateForm] = useState<CreateFormData>(EMPTY_FORM);

  const resetCreateForm = useCallback(() => {
    setCreateForm(EMPTY_FORM);
    setCreateFormErrors({});
    setCreateError(null);
    setCreateState("idle");
  }, []);

  const openCreateModal = useCallback(() => {
    resetCreateForm();
    setIsCreateModalOpen(true);
  }, [resetCreateForm]);

  const closeCreateModal = useCallback(() => {
    setIsCreateModalOpen(false);
    resetCreateForm();
  }, [resetCreateForm]);

  const handleFieldChange = useCallback((field: keyof CreateFormData, value: string) => {
    setCreateForm((prev) => ({ ...prev, [field]: value }));
    setCreateFormErrors((prev) => ({ ...prev, [field]: undefined }));
  }, []);

  const handleCreateCandidate = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const validationErrors = validateCreateCandidateForm(createForm);
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
        await onCreated();
        setCreateState("success");

        window.setTimeout(() => {
          closeCreateModal();
          router.replace("/", { scroll: false });
        }, 900);
      } catch (err) {
        setCreateState("error");
        setCreateError(err instanceof Error ? err.message : "No se pudo crear la candidatura.");
      }
    },
    [closeCreateModal, createForm, onCreated, router],
  );

  return {
    isCreateModalOpen,
    createState,
    createError,
    createFormErrors,
    createForm,
    openCreateModal,
    closeCreateModal,
    handleFieldChange,
    handleCreateCandidate,
  };
}
