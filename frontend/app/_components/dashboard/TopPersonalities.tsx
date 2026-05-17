import type { TopEntity } from '../../../lib/api'

type Meta = {
  role: string
  sentiment: 'positif' | 'mitigé' | 'négatif'
  trend: 'up' | 'flat' | 'down'
}

const SENTIMENT_COLOR: Record<Meta['sentiment'], string> = {
  positif: 'var(--positive)',
  mitigé: 'var(--warning)',
  négatif: 'var(--negative)',
}

const TREND = {
  up: { arrow: '↗', color: 'var(--warning)' },
  flat: { arrow: '→', color: 'var(--text-muted)' },
  down: { arrow: '↘', color: 'var(--positive)' },
} as const

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

export function TopPersonalities({
  entities,
  meta,
}: {
  entities: TopEntity[]
  /** Optional per-name extra fields. When provided for a name, the row renders the richer editorial layout. */
  meta?: Record<string, Meta>
}) {
  if (entities.length === 0) {
    return <p className="text-xs py-4" style={{ color: 'var(--text-muted)' }}>Aucune entité</p>
  }

  return (
    <div>
      {entities.slice(0, 6).map((e, i) => {
        const m = meta?.[e.name]
        const isLast = i === Math.min(entities.length, 6) - 1
        return (
          <div
            key={e.name}
            className="flex items-center gap-2.5 py-2"
            style={{ borderBottom: isLast ? 'none' : '1px solid var(--border-subtle)' }}
          >
            <div
              className="w-7 h-7 rounded-sm flex items-center justify-center text-[10px] font-semibold font-mono shrink-0"
              style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {initials(e.name)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>
                {e.name}
              </div>
              <div className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>
                {m?.role ?? `${e.count} mentions`}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-mono text-[11px] tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                {e.count}
              </div>
              {m && (
                <div className="flex items-center gap-1 justify-end mt-0.5">
                  <span className="w-1 h-1 rounded-full" style={{ background: SENTIMENT_COLOR[m.sentiment] }} />
                  <span className="font-mono text-[10px]" style={{ color: TREND[m.trend].color }}>
                    {TREND[m.trend].arrow}
                  </span>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
