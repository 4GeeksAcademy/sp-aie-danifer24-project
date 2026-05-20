export function LoadingSkeleton() {
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
