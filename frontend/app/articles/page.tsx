'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import Sidebar from '../../components/Sidebar'
import { fetchArticles, type Article } from '../../lib/api'
import { timeAgo, themeLabel } from '../../lib/formatters'
import { gravityColor, sentimentBucket, SENTIMENT_STYLE } from '../../lib/scales'

const PAGE_SIZE = 30

function sourceCode(source: string): string {
  const s = source.toLowerCase()
  if (s.includes('france') || s.includes('antilles')) return 'FA'
  if (s.includes('rci')) return 'RC'
  if (s.includes('guadeloupe') && s.includes('1')) return 'G1'
  if (s.includes('karib')) return 'KI'
  if (s.includes('outre')) return 'OM'
  return source.slice(0, 2).toUpperCase()
}

function sourceAccent(code: string): string {
  switch (code) {
    case 'G1': return 'var(--negative)'
    case 'FA': return 'var(--accent-link)'
    case 'KI': return 'var(--positive)'
    case 'RC': return 'var(--warning)'
    default: return 'var(--text-muted)'
  }
}

function ArticleRow({ a }: { a: Article }) {
  const src = sourceCode(a.source)
  const accent = sourceAccent(src)
  const gravity = Math.round((a.gravity_score || 0) * 100)
  const sent = a.sentiment || 'neutre'
  const sentS = SENTIMENT_STYLE[sentimentBucket(sent)]
  const entities = [...(a.elected || []), ...(a.institutions || [])].slice(0, 4)

  return (
    <article
      className="grid items-start gap-4 p-5"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        gridTemplateColumns: '52px minmax(0, 1fr) 180px',
      }}
    >
      <div
        className="w-11 h-11 rounded-md grid place-items-center font-mono text-[13px] font-semibold"
        style={{
          background: 'var(--bg-elevated)',
          border: `1px solid ${accent}40`,
          color: accent,
        }}
      >
        {src}
      </div>

      <div className="min-w-0">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{a.source}</span>
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>·</span>
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {timeAgo(a.date || a.scraped_at || '')}
          </span>
          {a.theme && (
            <>
              <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>·</span>
              <span
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                style={{
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {themeLabel(a.theme)}
              </span>
            </>
          )}
        </div>

        <h3
          className="font-serif text-[15px] font-semibold leading-snug mb-1.5 tracking-tight"
          style={{ color: 'var(--text)' }}
        >
          {a.url ? (
            <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
              {a.title}
            </a>
          ) : a.title}
        </h3>

        {a.content && (
          <p
            className="text-[13px] leading-relaxed mb-2.5 line-clamp-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            {a.content}
          </p>
        )}

        {entities.length > 0 && (
          <div className="flex gap-1.5 flex-wrap items-center">
            <span
              className="font-mono text-[10px] uppercase tracking-[0.12em] mr-1"
              style={{ color: 'var(--text-muted)' }}
            >
              Entités
            </span>
            {entities.map(e => (
              <span
                key={e}
                className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
                style={{
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {e}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col items-end gap-2.5">
        <span
          className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-sm"
          style={{ background: sentS.bg, color: sentS.color, border: `1px solid ${sentS.border}` }}
        >
          <span className="w-1 h-1 rounded-full" style={{ background: sentS.color }} />
          {sent}
        </span>
        <div className="flex items-baseline gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            Gravité
          </span>
          <span
            className="font-serif text-base font-semibold tabular-nums"
            style={{ color: gravityColor(gravity) }}
          >
            {gravity}
          </span>
        </div>
        {a.is_affair && (
          <span className="font-mono text-[10px]" style={{ color: 'var(--accent-link)' }}>
            ↗ Affaire
          </span>
        )}
        {a.url && (
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-auto inline-flex items-center gap-1 text-[11px] font-medium hover:underline"
            style={{ color: 'var(--text-secondary)' }}
          >
            Lire
            <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="m9 6 6 6-6 6" />
            </svg>
          </a>
        )}
      </div>
    </article>
  )
}

export default function ArticlesPage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState<string>('all')
  const [themeFilter, setThemeFilter] = useState<string>('all')

  const loadArticles = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchArticles(PAGE_SIZE, page * PAGE_SIZE)
      setArticles(data.articles || [])
      setTotal(data.total || 0)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { loadArticles() }, [loadArticles])

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    articles.forEach(a => {
      const s = a.source || 'inconnu'
      counts[s] = (counts[s] || 0) + 1
    })
    return counts
  }, [articles])

  const themeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    articles.forEach(a => {
      if (!a.theme) return
      counts[a.theme] = (counts[a.theme] || 0) + 1
    })
    return counts
  }, [articles])

  const filtered = useMemo(() => {
    return articles.filter(a => {
      if (sourceFilter !== 'all' && a.source !== sourceFilter) return false
      if (themeFilter !== 'all' && a.theme !== themeFilter) return false
      if (search) {
        const q = search.toLowerCase()
        const haystack = `${a.title || ''} ${a.source || ''} ${a.theme || ''} ${a.content || ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [articles, search, sourceFilter, themeFilter])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header
          className="px-6 lg:px-8 pt-5 pb-5"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Pilotage / Articles
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Articles
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                <span style={{ color: 'var(--text)' }}>{total}</span> articles indexés ·{' '}
                {filtered.length !== articles.length && (
                  <span><span style={{ color: 'var(--text)' }}>{filtered.length}</span> filtrés · </span>
                )}
                7 derniers jours
              </p>
            </div>
            <button
              onClick={loadArticles}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-press"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 0115.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.3L3 16M3 21v-5h5" />
              </svg>
              Actualiser
            </button>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto space-y-4">
          {/* Search + sources */}
          <div className="flex gap-3 items-center flex-wrap">
            <div
              className="relative flex-1 min-w-[260px] max-w-[460px]"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24" style={{ color: 'var(--text-muted)' }}>
                <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
              </svg>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={`Rechercher dans ${articles.length} articles…`}
                className="w-full bg-transparent pl-9 pr-3 py-2 text-sm focus:outline-none"
                style={{ color: 'var(--text)' }}
              />
            </div>

            <div className="flex gap-1.5 flex-wrap">
              <Chip active={sourceFilter === 'all'} onClick={() => setSourceFilter('all')}>
                Toutes <span style={{ color: 'var(--text-muted)' }}>{articles.length}</span>
              </Chip>
              {Object.entries(sourceCounts).slice(0, 6).map(([src, count]) => {
                const code = sourceCode(src)
                return (
                  <Chip key={src} active={sourceFilter === src} onClick={() => setSourceFilter(src)}>
                    <span className="w-1.5 h-1.5 rounded-full mr-1.5" style={{ background: sourceAccent(code) }} />
                    {src} <span style={{ color: 'var(--text-muted)' }}>{count}</span>
                  </Chip>
                )
              })}
            </div>
          </div>

          {/* Theme filters */}
          <div className="flex gap-1.5 flex-wrap items-center">
            <span
              className="font-mono text-[10px] uppercase tracking-[0.12em] mr-1"
              style={{ color: 'var(--text-muted)' }}
            >
              Thème
            </span>
            <Chip active={themeFilter === 'all'} onClick={() => setThemeFilter('all')}>
              Tous <span style={{ color: 'var(--text-muted)' }}>{articles.length}</span>
            </Chip>
            {Object.entries(themeCounts).slice(0, 8).map(([t, count]) => (
              <Chip key={t} active={themeFilter === t} onClick={() => setThemeFilter(t)}>
                {themeLabel(t)} <span style={{ color: 'var(--text-muted)' }}>{count}</span>
              </Chip>
            ))}
          </div>

          {error && (
            <div
              className="px-4 py-3 text-xs"
              style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
            >
              {error}
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <div className="skeleton h-4 w-2/3 mb-2" />
                  <div className="skeleton h-3 w-1/3" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div
              className="p-16 text-center"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
            >
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                {search ? `Aucun article pour "${search}"` : 'Aucun article trouvé'}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {filtered.map(a => <ArticleRow key={a._id} a={a} />)}
            </div>
          )}

          {/* Pagination */}
          {!loading && total > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-4">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                ← Précédent
              </button>
              <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                Page {page + 1} / {Math.ceil(total / PAGE_SIZE)}
              </span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={(page + 1) * PAGE_SIZE >= total}
                className="px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100 disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                Suivant →
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function Chip({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-full transition-colors"
      style={{
        background: active ? 'var(--accent-press)' : 'var(--bg-surface)',
        color: active ? 'var(--on-accent)' : 'var(--text-secondary)',
        border: `1px solid ${active ? 'var(--accent-press)' : 'var(--border)'}`,
      }}
    >
      {children}
    </button>
  )
}
