import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getRecords } from "@/services/api";
import { useDebounce } from "@/hooks/useDebounce";
import { RECORDS_LIMIT } from "@/lib/candidate-constants";
import { recordsFromResponse } from "@/lib/candidate-utils";
import type { RecordOut } from "@/types/candidates";

export function useCandidatesList() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const searchParamsRef = useRef(searchParams);
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
  const debouncedInputValue = useDebounce(inputValue, 300);

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

  useEffect(() => {
    searchParamsRef.current = searchParams;
    const nextSearch = searchParams.get("search") ?? "";
    setInputValue(nextSearch);
  }, [searchParams]);

  useEffect(() => {
    updateParams({ search: debouncedInputValue, page: 1 });
  }, [debouncedInputValue, updateParams]);

  const filteredRecords = useMemo(() => {
    return records.filter((candidate) => {
      const matchesStatus = statusFilter === "all" || candidate.status === statusFilter;
      const matchesStage = stageFilter === "all" || candidate.stage === stageFilter;

      const query = debouncedInputValue.trim().toLowerCase();
      const matchesSearch =
        query.length === 0 ||
        candidate.full_name.toLowerCase().includes(query) ||
        candidate.email.toLowerCase().includes(query);

      return matchesStatus && matchesStage && matchesSearch;
    });
  }, [debouncedInputValue, records, stageFilter, statusFilter]);

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

  return {
    records: filteredRecords,
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
  };
}
