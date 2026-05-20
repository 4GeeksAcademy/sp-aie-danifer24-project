export function DetailsSkeleton() {
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
