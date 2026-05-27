"use client";

import { PlusIcon } from "@/components/icons";
import CandidatesFilters from "@/components/CandidatesFilters";
import CandidatesTable from "@/components/CandidatesTable";
import CreateCandidateModal from "@/components/CreateCandidateModal";
import { useCandidatesList } from "@/hooks/useCandidatesList";
import { useCreateCandidateForm } from "@/hooks/useCreateCandidateForm";

export default function HomePage() {
  const {
    records,
    totalRecords,
    isLoading,
    error,
    statusFilter,
    stageFilter,
    currentPage,
    totalPages,
    pageNumbers,
    pageStart,
    pageEnd,
    hasRecords,
    detailQuery,
    inputValue,
    setInputValue,
    updateParams,
    fetchRecords,
  } = useCandidatesList();

  const {
    isCreateModalOpen,
    createState,
    createError,
    createFormErrors,
    createForm,
    openCreateModal,
    closeCreateModal,
    handleFieldChange,
    handleCreateCandidate,
  } = useCreateCandidateForm({
    onCreated: fetchRecords,
  });

  return (
    <main className="mx-auto w-full max-w-[1240px] px-6 py-8">
      <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-[44px] font-semibold leading-[1.1] tracking-[-0.02em] text-[#191B25]">
            Gestión de Talentos
          </h1>
        </div>
        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center gap-2 rounded-lg bg-[#0037D0] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#1B4DFF]"
        >
          <PlusIcon />
          Nueva Candidatura
        </button>
      </header>

      <CandidatesFilters
        inputValue={inputValue}
        onSearchChange={setInputValue}
        statusFilter={statusFilter}
        stageFilter={stageFilter}
        onStatusChange={(value) => updateParams({ status: value, page: 1 })}
        onStageChange={(value) => updateParams({ stage: value, page: 1 })}
      />

      <CandidatesTable
        isLoading={isLoading}
        error={error}
        hasRecords={hasRecords}
        records={records}
        detailQuery={detailQuery}
        pageStart={pageStart}
        pageEnd={pageEnd}
        totalRecords={totalRecords}
        currentPage={currentPage}
        totalPages={totalPages}
        pageNumbers={pageNumbers}
        onRetry={() => {
          void fetchRecords();
        }}
        onPageChange={(page) => updateParams({ page })}
      />

      <CreateCandidateModal
        isOpen={isCreateModalOpen}
        onClose={closeCreateModal}
        formData={createForm}
        formErrors={createFormErrors}
        submitState={createState}
        submitError={createError}
        onFieldChange={handleFieldChange}
        onSubmit={handleCreateCandidate}
      />
    </main>
  );
}
