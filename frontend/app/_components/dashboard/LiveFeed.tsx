import Link from 'next/link'
import type { Affair } from '../../../lib/api'
import { timeAgo, themeLabel } from '../../../lib/formatters'

type Item = {
  id: string
  time: string
  source?: string
  title: string
  severity: 'crit' | 'warn' | 'caution' | 'ok' | 'info'
  href?: string
}

function affairsToFeed(affairs: Affair[]): Item[] {
  return affairs
    .filter(a => a.last_activity || a.created_at)
    .sort((a, b) => {
      const ta = new Date(a.last_activity || a.created_at).getTime()
      const tb = new Date(b.last_activity || b.created_at).getTime()
      return tb - ta
    })
    .slice(0, 8)
    .map(a => {
      const g = a.gravity_score || 0
      const sev: Item['severity'] =
        g >= 0.7 ? 'crit' : g >= 0.5 ? 'warn' : g >= 0.3 ? 'caution' : 'ok'
      return {
        id: a._id,
        time: timeAgo(a.last_activity || a.created_at),
        source: themeLabel(a.theme || 'general'),
        title: a.title || a.primary_entity || 'Affaire',
        severity: sev,
        href: `/affairs/${a._id}`,
      }
    })
}

function sevColor(s: Item['severity']) {
  switch (s) {
    case 'crit': return 'var(--negative)'
    case 'warn': return 'var(--warning)'
    case 'caution': return 'var(--caution)'
    case 'ok': return 'var(--positive)'
    case 'info': return 'var(--accent-link)'
  }
}

export function LiveFeed({ affairs, isMock }: { affairs: Affair[]; isMock?: boolean }) {
  const items = affairsToFeed(affairs)

  return (
    <div
      className="flex flex-col"
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
            Flux temps réel
          </span>
          {isMock && (
            <span
              className="font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm"
              style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
            >
              Aperçu
            </span>
          )}
        </div>
        <span
          className="inline-flex items-center gap-1.5 font-mono text-[10px]"
          style={{ color: isMock ? 'var(--text-muted)' : 'var(--positive)' }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: isMock ? 'var(--text-muted)' : 'var(--positive)' }}
          />
          {isMock ? 'OFFLINE' : 'LIVE'}
        </span>
      </div>
      <div className="flex-1">
        {items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <div className="flag-stripe w-8 mb-3 opacity-60" />
            <p className="font-serif text-sm italic" style={{ color: 'var(--text-secondary)' }}>
              Aucune activité récente
            </p>
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Le fil se met à jour automatiquement
            </p>
          </div>
        )}
        {items.map((item, i) => {
          const inner = (
            <div className="flex gap-2.5">
              <span
                className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                style={{ background: sevColor(item.severity) }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 mb-1">
                  <span
                    className="font-mono text-[10px] tabular-nums"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {item.time}
                  </span>
                  {item.source && (
                    <span
                      className="text-[10px] font-semibold"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {item.source}
                    </span>
                  )}
                </div>
                <p
                  className="text-xs leading-snug line-clamp-2"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {item.title}
                </p>
              </div>
            </div>
          )
          const className = "block px-3.5 py-2.5 transition-colors hover:bg-ink-100"
          const style = { borderBottom: i < items.length - 1 ? '1px solid var(--border-subtle)' : 'none' as const }
          return item.href ? (
            <Link key={item.id} href={item.href} className={className} style={style}>
              {inner}
            </Link>
          ) : (
            <div key={item.id} className={className} style={style}>
              {inner}
            </div>
          )
        })}
      </div>
    </div>
  )
}
