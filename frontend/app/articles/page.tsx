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
  if (!s) return 'text-slate-500'
  const l = s.toLowerCase()
  if (l.includes('positif') || l.includes('positive')) return 'text-emerald-400'
  if (l.includes('négatif') || l.includes('negative')) return 'text-red-400'
  return 'text-slate-400'
}

function sentimentBg(s?: string): string {
  if (!s) return 'bg-slate-700/30'
  const l = s.toLowerCase()
  if (l.includes('positif') || l.includes('positive')) return 'bg-emerald-500/10 border-emerald-500/20'
  if (l.includes('négatif') || l.includes('negative')) return 'bg-red-500/10 border-red-500/20'
  return 'bg-slate-700/20 border-slate-700/30'
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
  if (!theme) return 'bg-slate-500/20 text-slate-400 border-slate-500/30'
  const map: Record<string, string> = {
    politique: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    economie: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    social: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    sante: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
    justice: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    securite: 'bg-red-500/20 text-red-400 border-red-500/30',
  }
  return map[theme] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'
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
      <main className="ml-64 flex-1 p-8 min-h-screen">
        <div className="max-w-7xl mx-auto animate-fade-in">

          {/* ── Header ──────────────────────────── */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white">Articles</h1>
              <p className="text-sm text-slate-400 mt-0.5">
                {total} article{total > 1 ? 's' : ''} en base
              </p>
            </div>
            <button
              onClick={loadArticles}
              className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-sm hover:bg-slate-700 transition-colors"
            >
              Actualiser
            </button>
          </div>

          {/* ── Search + Source badges ──────────── */}
          <div className="flex flex-wrap items-center gap-3 mb-6 p-4 bg-slate-800/30 rounded-xl border border-slate-700/30">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Rechercher un article..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-slate-900/50 border border-slate-700/50 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>

            {/* Source badges */}
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(sourceCounts).slice(0, 6).map(([src, count]) => (
                <span key={src} className="text-[10px] px-2 py-1 rounded-full bg-slate-700/30 text-slate-400 border border-slate-700/50">
                  {src} ({count})
                </span>
              ))}
            </div>
          </div>

          {/* ── Error ───────────────────────────── */}
          {error && (
            <div className="mb-6 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* ── Loading ─────────────────────────── */}
          {loading ? (
            <div className="space-y-3">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
                  <div className="skeleton h-4 w-2/3 mb-2" />
                  <div className="skeleton h-3 w-1/3" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="bg-slate-800/30 rounded-xl border border-slate-700/30 p-16 text-center">
              <svg className="w-12 h-12 mx-auto text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
              </svg>
              <p className="text-slate-500 text-sm">
                {search ? `Aucun article pour "${search}"` : 'Aucun article trouvé'}
              </p>
            </div>
          ) : (
            /* ── Article list ──────────────── */
            <div className="space-y-3">
              {filtered.map((article) => (
                <div key={article._id} className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 card-hover">
                  <div className="flex items-start gap-4">
                    {/* Source icon */}
                    <div className="w-10 h-10 rounded-lg bg-slate-700/50 flex items-center justify-center text-xs font-bold text-slate-400 flex-shrink-0">
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
                            <span className="text-slate-500">{article.source}</span>
                            <span className="text-slate-700">|</span>
                            <span className="text-slate-500">{timeAgo(article.date || article.scraped_at || '')}</span>
                            {article.theme && (
                              <>
                                <span className="text-slate-700">|</span>
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
                              article.gravity_score >= 0.8 ? 'text-red-400' :
                              article.gravity_score >= 0.5 ? 'text-orange-400' : 'text-slate-500'
                            }`}>
                              Gravité {Math.round(article.gravity_score * 100)}%
                            </span>
                          )}
                          {article.is_affair && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-400 border border-sky-500/20">
                              Affaire
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Entities */}
                      {(article.elected || article.institutions) && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {(article.elected || []).map((e, i) => (
                            <span key={`e-${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                              {e}
                            </span>
                          ))}
                          {(article.institutions || []).map((e, i) => (
                            <span key={`i-${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400">
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
                          className="inline-flex items-center gap-1 text-[10px] text-sky-500 hover:text-sky-400 mt-2"
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
                className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-xs disabled:opacity-30 hover:bg-slate-700 transition-colors"
              >
                Précédent
              </button>
              <span className="text-xs text-slate-500">
                Page {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 text-xs disabled:opacity-30 hover:bg-slate-700 transition-colors"
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
