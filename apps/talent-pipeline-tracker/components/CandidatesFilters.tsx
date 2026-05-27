import { ChevronIcon, SearchIcon } from "@/components/icons";
import { LIST_STAGE_OPTIONS, LIST_STATUS_OPTIONS } from "@/lib/candidate-constants";

interface CandidatesFiltersProps {
  inputValue: string;
  onSearchChange: (value: string) => void;
  statusFilter: string;
  stageFilter: string;
  onStatusChange: (value: string) => void;
  onStageChange: (value: string) => void;
}

export default function CandidatesFilters({
  inputValue,
  onSearchChange,
  statusFilter,
  stageFilter,
  onStatusChange,
  onStageChange,
}: CandidatesFiltersProps) {
  return (
    <section className="mb-3 rounded-xl border border-[#C4C5D9] bg-white p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-center">
        <div className="relative flex-1">
          <input
            placeholder="Buscar por nombre o puesto..."
            value={inputValue}
            onChange={(event) => onSearchChange(event.target.value)}
            className="w-full rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] py-3 pl-11 pr-4 text-sm text-[#191B25] placeholder:text-[#747688]"
          />
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#747688]">
            <SearchIcon />
          </span>
        </div>

        <div className="flex w-full gap-3 md:w-auto">
          <div className="relative w-full md:w-[146px]">
            <select
              value={statusFilter}
              onChange={(event) => onStatusChange(event.target.value)}
              className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
            >
              {LIST_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#434656]">
              <ChevronIcon direction="down" />
            </span>
          </div>

          <div className="relative w-full md:w-[146px]">
            <select
              value={stageFilter}
              onChange={(event) => onStageChange(event.target.value)}
              className="w-full appearance-none rounded-lg border border-[#C4C5D9] bg-[#F3F2FF] px-4 py-3 pr-8 text-sm text-[#434656]"
            >
              {LIST_STAGE_OPTIONS.map((option) => (
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
  );
}
