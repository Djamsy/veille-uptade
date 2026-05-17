'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import { fetchAffairs, type Affair } from '../../lib/api'
import { timeAgo, themeLabel } from '../../lib/formatters'

type Priority = 'hot' | 'watch' | 'minor'
type StatusFilter = 'all' | 'active' | 'stale' | 'archived'
type SortField = 'bmg' | 'gravity' | 'recent' | 'items'
type ViewMode = 'grid' | 'list'

const PRIORITY_META: Record<Priority, { label: string; color: string }> = {
  hot:   { label: 'Urgentes',     color: 'var(--negative)' },
  watch: { label: 'À surveiller', color: 'var(--caution)' },
  minor: { label: 'Mineures',     color: 'var(--positive)' },
}

function scoreColor(bmg: number): string {
  if (bmg >= 70) return 'var(--negative)'
  if (bmg >= 50) return 'var(--warning)'
  if (bmg >= 25) return 'var(--caution)'
  return 'var(--positive)'
}

function sevLabel(bmg: number): string {
  if (bmg >= 70) return 'CRITIQUE'
  if (bmg >= 50) return 'ÉLEVÉ'
  if (bmg >= 25) return 'MODÉRÉ'
  return 'FAIBLE'
}

type SentimentKind = 'crit' | 'warn' | 'caution' | 'ok' | 'neutral'
function sentimentKind(s?: string): SentimentKind {
  const l = (s || '').toLowerCase()
  if (l.startsWith('très négatif') || l.startsWith('tres negatif')) return 'crit'
  if (l.includes('négatif') || l.includes('negatif')) return 'warn'
  if (l.includes('mitigé') || l.includes('mixte')) return 'caution'
  if (l.includes('positif')) return 'ok'
  return 'neutral'
}

const SENTIMENT_STYLE: Record<SentimentKind, { bg: string; color: string; border: string }> = {
  crit:    { bg: 'var(--crit-soft)',   color: '#b02939', border: '#f5d4d9' },
  warn:    { bg: 'var(--warn-soft)',   color: '#9d551f', border: '#f3dcc5' },
  caution: { bg: 'var(--caution-soft)',color: '#8a7218', border: '#ecdfa9' },
  ok:      { bg: 'var(--ok-soft)',     color: '#3d6f44', border: '#cce5d0' },
  neutral: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)', border: 'var(--border)' },
}

function getAffairPriority(a: Affair): Priority {
  if (a.priority === 'hot' || a.priority === 'watch' || a.priority === 'minor') return a.priority
  const g = a.gravity_score || 0
  const bmg = a.bmg || 0
  const items = a.item_count || 1
  if (g >= 0.75) return 'hot'
  if (bmg >= 0.65 && items >= 2) return 'hot'
  if (g >= 0.55) return 'watch'
  if (bmg >= 0.35 && items >= 2) return 'watch'
  return 'minor'
}

function AffaireCard({ a }: { a: Affair }) {
  const bmg = Math.round((a.bmg || 0) * 100)
  const c = scoreColor(bmg)
  const sentS = SENTIMENT_STYLE[sentimentKind(a.sentiment)]
  const loc = a.primary_entity || a.institutions?.[0] || '—'
  const tags = [...(a.elected || []), ...(a.institutions || [])].slice(0, 3)

  return (
    <Link href={`/affairs/${a._id}`}>
      <article
        className="relative flex flex-col h-full transition-colors hover:bg-ink-100"
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          overflow: 'hidden',
        }}
      >
        <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: c }} />

        <div className="flex items-start gap-3 pl-[18px] pr-4 pt-3.5 pb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="font-mono text-[10px] font-semibold tracking-[0.1em]" style={{ color: c }}>
                {sevLabel(bmg)} · BMG {bmg}
              </span>
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>·</span>
              <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {themeLabel(a.theme)}
              </span>
            </div>
            <h3
              className="font-serif text-[15px] font-semibold leading-snug tracking-tight"
              style={{ color: 'var(--text)' }}
            >
              {a.title || a.primary_entity || 'Affaire'}
            </h3>
          </div>
          <div className="text-right shrink-0">
            <div className="font-serif text-[26px] font-semibold tabular-nums leading-none" style={{ color: c, letterSpacing: '-0.02em' }}>
              {bmg}
            </div>
            <div className="font-mono text-[9px] uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--text-muted)' }}>
              BMG
            </div>
          </div>
        </div>

        {a.description && (
          <p className="text-[13px] leading-relaxed pl-[18px] pr-4 pb-3 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
            {a.description}
          </p>
        )}

        <div className="pl-[18px] pr-4 pb-3 flex gap-1.5 flex-wrap">
          {a.sentiment && (
            <span
              className="inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: sentS.bg, color: sentS.color, border: `1px solid ${sentS.border}` }}
            >
              <span className="w-1 h-1 rounded-full" style={{ background: sentS.color }} />
              {a.sentiment}
            </span>
          )}
          {tags.map(t => (
            <span
              key={t}
              className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            >
              {t}
            </span>
          ))}
        </div>

        <div
          className="mt-auto flex items-center justify-between pl-[18px] pr-4 py-2.5 font-mono text-[11px]"
          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
        >
          <span style={{ color: 'var(--text-secondary)' }} className="font-sans truncate max-w-[60%]">{loc}</span>
          <span className="tabular-nums">{a.item_count || 0} items · {(a.sources || []).length} src · {timeAgo(a.last_activity || a.created_at)}</span>
        </div>
      </article>
    </Link>
  )
}

export default function AffairsPage() {
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [sortBy, setSortBy] = useState<SortField>('bmg')
  const [search, setSearch] = useState('')
  const [themeFilter, setThemeFilter] = useState<string>('all')
  const [viewMode] = useState<ViewMode>('grid')

  const loadAffairs = useCallback(async () => {
    setLoading(true)
    try {
      const apiStatus = statusFilter === 'all' ? 'active' : statusFilter
      const data = await fetchAffairs(apiStatus, 50, sortBy === 'recent' ? 'last_activity' : sortBy)
      setAffairs(data.affairs || [])
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, sortBy])

  useEffect(() => { loadAffairs() }, [loadAffairs])

  const filtered = useMemo(() => {
    return affairs.filter(a => {
      if (themeFilter !== 'all' && a.theme !== themeFilter) return false
      if (search) {
        const q = search.toLowerCase()
        const haystack = `${a.title || ''} ${a.primary_entity || ''} ${a.description || ''} ${a.theme}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [affairs, search, themeFilter])

  const grouped = useMemo(() => {
    const hot: Affair[] = []
    const watch: Affair[] = []
    const minor: Affair[] = []
    filtered.forEach(a => {
      const p = getAffairPriority(a)
      if (p === 'hot') hot.push(a)
      else if (p === 'watch') watch.push(a)
      else minor.push(a)
    })
    return { hot, watch, minor }
  }, [filtered])

  const totalAll = affairs.length
  const totalHot = grouped.hot.length
  const totalWatch = grouped.watch.length
  const avgBmg = affairs.length > 0
    ? Math.round(affairs.reduce((s, a) => s + (a.bmg || 0), 0) / affairs.length * 100)
    : 0

  const themeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    affairs.forEach(a => { if (a.theme) counts[a.theme] = (counts[a.theme] || 0) + 1 })
    return counts
  }, [affairs])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Pilotage / Affaires
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Affaires
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                <span style={{ color: 'var(--text)' }}>{totalAll}</span> affaires au total
                {totalHot > 0 && <span> — <span style={{ color: 'var(--negative)' }}>{totalHot} urgentes</span></span>}
              </p>
            </div>
            <button
              onClick={loadAffairs}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 0115.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.3L3 16M3 21v-5h5" />
              </svg>
              Actualiser
            </button>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto space-y-5">
          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCell label="Total suivies" value={totalAll} hint="active filter" />
            <KpiCell label="Urgentes · BMG ≥ 70" value={totalHot} severity="crit" hint={`${totalHot > 0 ? '+' : ''}${totalHot} vs hier`} />
            <KpiCell label="À surveiller" value={totalWatch} severity="warn" />
            <KpiCell label="BMG moyen" value={avgBmg} severity="neutral" />
          </div>

          {/* Toolbar */}
          <div className="flex gap-3 items-center flex-wrap">
            <div
              className="relative flex-1 min-w-[260px] max-w-[420px]"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}
            >
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24" style={{ color: 'var(--text-muted)' }}>
                <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
              </svg>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Rechercher une affaire, entité, élu…"
                className="w-full bg-transparent pl-9 pr-3 py-2 text-sm focus:outline-none"
                style={{ color: 'var(--text)' }}
              />
            </div>

            <Segmented
              value={statusFilter}
              onChange={v => setStatusFilter(v as StatusFilter)}
              options={[
                { value: 'all', label: 'Toutes' },
                { value: 'active', label: 'Actives' },
                { value: 'stale', label: 'En veille' },
                { value: 'archived', label: 'Archivées' },
              ]}
            />

            <div className="ml-auto flex gap-2">
              <SelectField value={sortBy} onChange={v => setSortBy(v as SortField)}>
                <option value="bmg">BMG décroissant</option>
                <option value="gravity">Gravité</option>
                <option value="recent">Plus récent</option>
                <option value="items">Plus d&apos;items</option>
              </SelectField>
              <SelectField value={themeFilter} onChange={setThemeFilter}>
                <option value="all">Tous thèmes</option>
                {Object.keys(themeCounts).map(t => (
                  <option key={t} value={t}>{themeLabel(t)} ({themeCounts[t]})</option>
                ))}
              </SelectField>
            </div>
          </div>

          {error && (
            <div className="px-4 py-3 text-xs" style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}>
              {error}
            </div>
          )}

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <div className="skeleton h-4 w-2/3 mb-3" />
                  <div className="skeleton h-3 w-full mb-2" />
                  <div className="skeleton h-3 w-3/4" />
                </div>
              ))}
            </div>
          ) : (
            <>
              {grouped.hot.length > 0 && <Section meta={PRIORITY_META.hot} count={grouped.hot.length} affairs={grouped.hot} />}
              {grouped.watch.length > 0 && <Section meta={PRIORITY_META.watch} count={grouped.watch.length} affairs={grouped.watch} />}
              {grouped.minor.length > 0 && <Section meta={PRIORITY_META.minor} count={grouped.minor.length} affairs={grouped.minor} />}
              {filtered.length === 0 && (
                <div className="p-16 text-center" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Aucune affaire</p>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function Section({ meta, count, affairs }: { meta: { label: string; color: string }; count: number; affairs: Affair[] }) {
  return (
    <section>
      <div className="flex items-baseline gap-2.5 mb-3">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.color }} />
        <h2 className="font-serif text-base font-semibold tracking-tight" style={{ color: 'var(--text)' }}>{meta.label}</h2>
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {count} affaire{count > 1 ? 's' : ''}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
        {affairs.map(a => <AffaireCard key={a._id} a={a} />)}
      </div>
    </section>
  )
}

function KpiCell({ label, value, severity, hint }: { label: string; value: number | string; severity?: 'crit' | 'warn' | 'ok' | 'neutral'; hint?: string }) {
  const isCrit = severity === 'crit'
  const color = isCrit ? 'var(--negative)' : severity === 'warn' ? 'var(--warning)' : severity === 'ok' ? 'var(--positive)' : 'var(--text)'
  return (
    <div
      className="p-4"
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${isCrit ? '#f5d4d9' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
      }}
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: isCrit ? 'var(--negative)' : 'var(--text-muted)' }}>
        {label}
      </div>
      <div className="flex items-baseline gap-2.5">
        <span className="font-serif text-3xl font-semibold tabular-nums leading-none" style={{ color }}>
          {value}
        </span>
        {hint && (
          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</span>
        )}
      </div>
    </div>
  )
}

function Segmented({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div
      className="inline-flex"
      style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)' }}
    >
      {options.map((opt, i) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-3 py-1.5 text-xs font-medium"
          style={{
            background: value === opt.value ? 'var(--bg-hover)' : 'transparent',
            color: value === opt.value ? 'var(--text)' : 'var(--text-muted)',
            borderLeft: i > 0 ? '1px solid var(--border)' : 'none',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function SelectField({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="text-xs font-medium px-2.5 py-1.5 rounded-sm appearance-none cursor-pointer"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        color: 'var(--text-secondary)',
        paddingRight: '24px',
        backgroundImage: 'linear-gradient(45deg, transparent 50%, currentColor 50%), linear-gradient(135deg, currentColor 50%, transparent 50%)',
        backgroundPosition: 'calc(100% - 14px) 50%, calc(100% - 10px) 50%',
        backgroundSize: '4px 4px',
        backgroundRepeat: 'no-repeat',
      }}
    >
      {children}
    </select>
  )
}
