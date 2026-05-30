export function TrendArrow({ pct }: { pct: number }) {
  if (pct === 0) {
    return <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>—</span>
  }
  const up = pct > 0
  return (
    <span
      className="text-[10px] font-semibold flex items-center gap-0.5"
      style={{ color: up ? '#34d399' : '#f87171' }}
    >
      <svg
        className="w-3 h-3"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        style={{ transform: up ? 'rotate(0)' : 'rotate(180deg)' }}
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      </svg>
      {Math.abs(pct)}%
    </span>
  )
}
