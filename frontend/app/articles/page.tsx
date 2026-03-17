'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import { fetchArticles, type Article } from '../../lib/api'

// ── Helpers ──────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

function sentimentColor(s?: string): string {
  if (!s) return 'text-[rgba(255,255,255,0.4)]'
  const l = s.toLowerCase()
  if (l.includes('positif') || l.includes('positive')) return 'text-[#34d399]'
  if (l.includes('négatif') || l.includes('negative')) return 'text-[#f87171]'
  return 'text-[rgba(255,255,255,0.4)]'
}

function sentimentBg(s?: string): string {
  if (!s) return 'bg-[rgba(255,255,255,0.04)] border-[rgba(255,255,255,0.08)]'
  const l = s.toLowerCase()
  if (l.includes('positif') || l.includes('positive')) return 'bg-[rgba(16,185,129,0.1)] border-[rgba(16,185,129,0.3)]'
  if (l.includes('négatif') || l.includes('negative')) return 'bg-[rgba(239,68,68,0.1)] border-[rgba(239,68,68,0.3)]'
  return 'bg-[rgba(255,255,255,0.04)] border-[rgba(255,255,255,0.08)]'
}

function themeLabel(theme?: string): string {
  if (!theme) return 'Général'
  const map: Record<string, string> = {
    politique: 'Politique', economie: 'Économie', social: 'Social',
    environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
    education: 'Éducation', culture: 'Culture', sport: 'Sport',
    securite: 'Sécurité', infrastructure: 'Infrastructure', general: 'Général',
  }
  return map[theme] || theme
}

function themeColor(theme?: string): string {
  if (!theme) return 'bg-[rgba(255,255,255,0.04)] text-[rgba(255,255,255,0.35)] border-[rgba(255,255,255,0.06)]'
  const map: Record<string, string> = {
    politique: 'bg-[rgba(168,85,247,0.15)] text-[#c084fc] border-[rgba(168,85,247,0.3)]',
    economie: 'bg-[rgba(16,185,129,0.1)] text-[#34d399] border-[rgba(16,185,129,0.3)]',
    social: 'bg-[rgba(96,165,250,0.1)] text-[#60a5fa] border-[rgba(96,165,250,0.3)]',
    sante: 'bg-[rgba(244,63,94,0.1)] text-[#f43f5e] border-[rgba(244,63,94,0.3)]',
    justice: 'bg-[rgba(251,146,60,0.1)] text-[#fb923c] border-[rgba(251,146,60,0.3)]',
    securite: 'bg-[rgba(239,68,68,0.1)] text-[#f87171] border-[rgba(239,68,68,0.3)]',
  }
  return map[theme] || 'bg-[rgba(255,255,255,0.04)] text-[rgba(255,255,255,0.35)] border-[rgba(255,255,255,0.06)]'
}

function sourceLogo(source: string): string {
  const s = source.toLowerCase()
  if (s.includes('france') || s.includes('antilles')) return 'FA'
  if (s.includes('rci')) return 'RC'
  if (s.includes('guadeloupe') && s.includes('1')) return 'G1'
  if (s.includes('carib')) return 'CB'
  if (s.includes('outre')) return 'OM'
  return source.slice(0, 2).toUpperCase()
}

// ════════════════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════════════════
export default function ArticlesPage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const PAGE_SIZE = 30

  const loadArticles = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchArticles(PAGE_SIZE, page * PAGE_SIZE)
      setArticles(data.articles || [])
      setTotal(data.total || 0)
      setError('')
    } catch (e: any) {
      setError(e.message || 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { loadArticles() }, [loadArticles])

  // Client-side search filter
  const filtered = search
    ? articles.filter(a =>
        (a.title || '').toLowerCase().includes(search.toLowerCase()) ||
        (a.source || '').toLowerCase().includes(search.toLowerCase()) ||
        (a.theme || '').toLowerCase().includes(search.toLowerCase())
      )
    : articles

  const totalPages = Math.ceil(total / PAGE_SIZE)

  // Group by source for stats
  const sourceCounts: Record<string, number> = {}
  articles.forEach(a => {
    const s = a.source || 'inconnu'
    sourceCounts[s] = (sourceCounts[s] || 0) + 1
  })

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-5 lg:p-8 min-h-screen">
        <div className="max-w-7xl mx-auto animate-fade-in">

          {/* ── Header ──────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
            <div>
              <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Articles</h1>
              <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.35)' }}>
                {total} article{total > 1 ? 's' : ''} en base
              </p>
            </div>
            <button
              onClick={loadArticles}
              className="btn-glass px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                Actualiser
              </span>
            </button>
          </div>

          {/* ── Search + Source badges ──────────── */}
          <div className="glass-card-static flex flex-wrap items-center gap-3 mb-6 p-4">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[rgba(255,255,255,0.35)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Rechercher un article..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="input-dark w-full pl-9 pr-3 py-2"
              />
            </div>

            {/* Source badges */}
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(sourceCounts).slice(0, 6).map(([src, count]) => (
                <span key={src} className="text-[10px] px-2 py-1 rounded-full text-[rgba(255,255,255,0.4)]" style={{ backgroundColor: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.08)', borderWidth: '1px' }}>
                  {src} ({count})
                </span>
              ))}
            </div>
          </div>

          {/* ── Error ───────────────────────────── */}
          {error && (
            <div className="mb-6 px-4 py-3 rounded-lg text-[#f87171] text-sm" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.3)', borderWidth: '1px' }}>
              {error}
            </div>
          )}

          {/* ── Loading ─────────────────────────── */}
          {loading ? (
            <div className="space-y-3">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="glass-card-static p-4">
                  <div className="skeleton h-4 w-2/3 mb-2" />
                  <div className="skeleton h-3 w-1/3" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="glass-card-static p-16 text-center">
              <svg className="w-12 h-12 mx-auto text-[rgba(255,255,255,0.35)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
              </svg>
              <p className="text-[rgba(255,255,255,0.35)] text-sm">
                {search ? `Aucun article pour "${search}"` : 'Aucun article trouvé'}
              </p>
            </div>
          ) : (
            /* ── Article list ──────────────── */
            <div className="space-y-3">
              {filtered.map((article) => (
                <div key={article._id} className="glass-card p-4 card-hover">
                  <div className="flex items-start gap-4">
                    {/* Source icon */}
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 text-[rgba(255,255,255,0.4)]" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
                      {sourceLogo(article.source)}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <h3 className="text-sm font-semibold text-white mb-1 line-clamp-2">
                            {article.title}
                          </h3>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="text-[rgba(255,255,255,0.6)]">{article.source}</span>
                            <span className="text-[rgba(255,255,255,0.25)]">|</span>
                            <span className="text-[rgba(255,255,255,0.6)]">{timeAgo(article.date || article.scraped_at || '')}</span>
                            {article.theme && (
                              <>
                                <span className="text-[rgba(255,255,255,0.25)]">|</span>
                                <span className={`badge border ${themeColor(article.theme)}`}>
                                  {themeLabel(article.theme)}
                                </span>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Right meta */}
                        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                          {article.sentiment && (
                            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${sentimentBg(article.sentiment)} ${sentimentColor(article.sentiment)}`}>
                              {article.sentiment}
                            </span>
                          )}
                          {article.gravity_score !== undefined && article.gravity_score > 0 && (
                            <span className={`text-[10px] font-medium ${
                              article.gravity_score >= 0.8 ? 'text-[#f87171]' :
                              article.gravity_score >= 0.5 ? 'text-[#fb923c]' : 'text-[rgba(255,255,255,0.3)]'
                            }`}>
                              Gravité {Math.round(article.gravity_score * 100)}%
                            </span>
                          )}
                          {article.is_affair && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded text-[#34d399]" style={{ backgroundColor: 'rgba(16,185,129,0.1)', borderColor: 'rgba(16,185,129,0.3)', borderWidth: '1px' }}>
                              Affaire
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Entities */}
                      {(article.elected || article.institutions) && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {(article.elected || []).map((e, i) => (
                            <span key={`e-${i}`} className="text-[10px] px-1.5 py-0.5 rounded text-[#c084fc]" style={{ backgroundColor: 'rgba(168,85,247,0.1)' }}>
                              {e}
                            </span>
                          ))}
                          {(article.institutions || []).map((e, i) => (
                            <span key={`i-${i}`} className="text-[10px] px-1.5 py-0.5 rounded text-[#34d399]" style={{ backgroundColor: 'rgba(16,185,129,0.1)' }}>
                              {e}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* URL */}
                      {article.url && (
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[10px] text-[#818cf8] hover:text-[#818cf8] mt-2"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                          Lire l'article
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── Pagination ──────────────────────── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-8">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="btn-glass px-3 py-1.5 text-xs disabled:opacity-30"
              >
                Précédent
              </button>
              <span className="text-xs text-[rgba(255,255,255,0.35)]">
                Page {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="btn-glass px-3 py-1.5 text-xs disabled:opacity-30"
              >
                Suivant
              </button>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
