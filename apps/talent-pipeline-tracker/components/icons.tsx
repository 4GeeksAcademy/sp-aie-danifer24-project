interface ChevronIconProps {
  direction?: "left" | "right" | "down";
}

export function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ChevronIcon({ direction = "down" }: ChevronIconProps) {
  const rotations: Record<string, string> = {
    left: "rotate-90",
    right: "-rotate-90",
    down: "rotate-0",
  };

  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-4 w-4 ${rotations[direction]}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
