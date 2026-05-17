// Radio captures sub-panel for the right rail (matches v3-check.jpg).
// Shows last captures with time + source + status (ok / crit when quota).

type Capture = {
  time: string
  source: string
  status: 'ok' | 'crit' | 'warn'
  note?: string
}

const MOCK_CAPTURES: Capture[] = [
  { time: '12h00', source: 'RCI', status: 'ok', note: 'il y a 4 h' },
  { time: '12h00', source: '1ère', status: 'ok', note: 'il y a 4 h' },
  { time: '7h00', source: '1ère', status: 'ok', note: 'il y a 8 h' },
  { time: '7h00', source: 'RCI', status: 'crit', note: 'quota' },
  { time: '6h20', source: 'RCI', status: 'crit', note: 'quota' },
]

function dot(status: Capture['status']): string {
  switch (status) {
    case 'ok': return 'var(--positive)'
    case 'warn': return 'var(--warning)'
    case 'crit': return 'var(--negative)'
  }
}

type Props = {
  todayCount?: number
  totalCount?: number
  /** When omitted, falls back to mock list. */
  captures?: Capture[]
  isMock?: boolean
}

export function RadioCapturesPanel({ todayCount, totalCount, captures, isMock }: Props) {
  const list = (captures && captures.length > 0) ? captures : MOCK_CAPTURES
  const mocked = isMock ?? (!captures || captures.length === 0)
  const today = todayCount ?? (mocked ? 4 : 0)
  const total = totalCount ?? (mocked ? 7 : 0)
  const treated = `${today} / ${total} traitées`

  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
      }}
    >
      <div
        className="flex items-center justify-between px-3.5 py-3"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-[10px] uppercase tracking-[0.14em]"
            style={{ color: 'var(--text-muted)' }}
          >
            Radio · Captures
          </span>
          {mocked && (
            <span
              className="font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm"
              style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
            >
              Aperçu
            </span>
          )}
        </div>
        <span
          className="font-mono text-[10px]"
          style={{ color: today < total ? 'var(--warning)' : 'var(--positive)' }}
        >
          {treated}
        </span>
      </div>
      <div className="px-3.5 py-3 space-y-2">
        {list.map((c, i) => (
          <div key={`${c.time}-${c.source}-${i}`} className="flex items-center gap-2.5 text-xs">
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: dot(c.status) }} />
            <span className="font-mono tabular-nums" style={{ color: 'var(--text)' }}>
              {c.time}
            </span>
            <span className="font-medium" style={{ color: 'var(--text-secondary)' }}>
              {c.source}
            </span>
            <span
              className="ml-auto font-mono text-[10px]"
              style={{ color: c.status === 'crit' ? 'var(--negative)' : 'var(--text-muted)' }}
            >
              {c.note}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
