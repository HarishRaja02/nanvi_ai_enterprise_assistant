export function BrandLogo({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      {/* Nanvi AI Luxury Geometric Obsidian Mark */}
      <div className="w-8 h-8 rounded-xl bg-black text-white flex items-center justify-center shadow-sm">
        <svg
          className="w-4 h-4 text-white"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
      </div>
      <div>
        <div className="flex items-center gap-1.5">
          <span className="font-serif text-xl font-normal text-neutral-900 tracking-tight">
            Nanvi
          </span>
          <span className="text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded bg-neutral-900 text-white uppercase">
            AI
          </span>
        </div>
        <p className="text-[9px] uppercase tracking-[0.18em] font-medium text-neutral-400">
          Enterprise Assistant Platform
        </p>
      </div>
    </div>
  );
}
