'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '../../../components/Sidebar'
import BmgGauge from '../../../components/BmgGauge'
import { fetchAffairDetail, recalculateBmg, type Affair, type TimelineEvent, type BmgDetails, type LinkedArticle, type LinkedRadio, type LinkedSocial } from '../../../lib/api'

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

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('fr-FR', {
      day: 'numeric', month: 'long', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return dateStr }
}

function themeLabel(theme: string): string {
  const map: Record<string, string> = {
    politique: 'Politique', economie: 'Économie', social: 'Social',
    environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
    education: 'Éducation', culture: 'Culture', sport: 'Sport',
    securite: 'Sécurité', infrastructure: 'Infrastructure', general: 'Général',
  }
  return map[theme] || theme
}

function themeColor(theme: string): string {
  const map: Record<string, string> = {
    politique: 'bg-purple-100 text-purple-600 border-purple-200',
    economie: 'bg-emerald-100 text-emerald-600 border-emerald-200',
    social: 'bg-blue-100 text-blue-400 border-blue-200',
    sante: 'bg-rose-100 text-rose-400 border-rose-200',
    justice: 'bg-amber-100 text-amber-600 border-amber-200',
    securite: 'bg-red-100 text-red-600 border-red-500/30',
  }
  return map[theme] || 'bg-slate-100 text-slate-500 border-slate-200'
}

// ── Canal bar ────────────────────────────────────────────
function CanalBar({ canal, value, max }: { canal: string; value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  const colors: Record<string, string> = {
    presse: 'bg-teal-500',
    radio: 'bg-amber-500',
    tv: 'bg-purple-500',
    social: 'bg-pink-500',
  }
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-500 w-14 capitalize">{canal}</span>
      <div className="flex-1 bg-slate-100 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${colors[canal] || 'bg-slate-500'} transition-all duration-500`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="text-xs text-slate-500 w-8 text-right">{value.toFixed(1)}</span>
    </div>
  )
}

// ── Timeline item ────────────────────────────────────────
function TimelineItem({ event }: { event: TimelineEvent }) {
  const iconByEvent: Record<string, string> = {
    created: 'text-emerald-600',
    promoted: 'text-teal-600',
    bmg_updated: 'text-amber-600',
    status_changed: 'text-purple-600',
    item_added: 'text-slate-500',
  }
  const color = iconByEvent[event.event] || 'text-slate-500'

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`w-2.5 h-2.5 rounded-full ${color.replace('text-', 'bg-')}`} />
        <div className="w-px flex-1 bg-slate-100" />
      </div>
      <div className="pb-4 flex-1">
        <p className="text-xs font-medium text-slate-500">{event.event.replace(/_/g, ' ')}</p>
        <p className="text-[10px] text-slate-500">{formatDate(event.timestamp)}</p>
        {event.details && Object.keys(event.details).length > 0 && (
          <div className="mt-1 text-[10px] text-slate-500 bg-white shadow-sm rounded p-2">
            {Object.entries(event.details).slice(0, 4).map(([k, v]) => (
              <div key={k}><span className="text-slate-500">{k}:</span> {String(v)}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════════════════
export default function AffairDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string

  const [affair, setAffair] = useState<Affair | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [bmgLive, setBmgLive] = useState<BmgDetails | null>(null)
  const [linkedArticles, setLinkedArticles] = useState<LinkedArticle[]>([])
  const [linkedRadio, setLinkedRadio] = useState<LinkedRadio[]>([])
  const [linkedSocial, setLinkedSocial] = useState<LinkedSocial[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [recalculating, setRecalculating] = useState(false)

  const loadDetail = useCallback(async () => {
    try {
      const data = await fetchAffairDetail(id)
      setAffair(data.affair)
      setTimeline(data.timeline || [])
      setBmgLive(data.bmg_live || null)
      setLinkedArticles(data.linked_articles || [])
      setLinkedRadio(data.linked_radio || [])
      setLinkedSocial(data.linked_social || [])
      setError('')
    } catch (e: any) {
      setError(e.message || 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { loadDetail() }, [loadDetail])

  const handleRecalculate = async () => {
    setRecalculating(true)
    try {
      const result = await recalculateBmg(id)
      if (result.bmg) setBmgLive(result.bmg)
      await loadDetail()
    } catch (e: any) {
      console.error('Recalculate error:', e)
    } finally {
      setRecalculating(false)
    }
  }

  // ── Loading ──────────────────────────────────────
  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen">
          <div className="max-w-5xl mx-auto">
            <div className="skeleton h-6 w-40 mb-6" />
            <div className="skeleton h-48 w-full mb-6 rounded-xl" />
            <div className="grid grid-cols-2 gap-4">
              <div className="skeleton h-32 rounded-xl" />
              <div className="skeleton h-32 rounded-xl" />
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (error || !affair) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen">
          <div className="max-w-5xl mx-auto text-center py-20">
            <p className="text-red-600 mb-4">{error || 'Affaire introuvable'}</p>
            <button onClick={() => router.push('/affairs')} className="text-teal-600 text-sm">
              Retour aux affaires
            </button>
          </div>
        </main>
      </div>
    )
  }

  const bmg = bmgLive || affair.bmg_details
  const maxCanal = bmg ? Math.max(...Object.values(bmg.bnp_by_canal || {}), 1) : 1

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen">
        <div className="max-w-5xl mx-auto animate-fade-in">

          {/* ── Breadcrumb ────────────────────── */}
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-6">
            <Link href="/affairs" className="hover:text-slate-500 transition-colors">Affaires</Link>
            <span>/</span>
            <span className="text-slate-500">{affair.title || affair.primary_entity}</span>
          </div>

          {/* ── Header Card ───────────────────── */}
          <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-6 mb-6">
            <div className="flex items-start justify-between gap-6">
              <div className="flex-1">
                <h1 className="text-xl font-bold text-slate-800 mb-2">
                  {affair.title || affair.primary_entity || 'Affaire'}
                </h1>
                {affair.description && (
                  <p className="text-sm text-slate-500 mb-4">{affair.description}</p>
                )}

                {/* Tags */}
                <div className="flex flex-wrap gap-2 mb-4">
                  <span className={`badge border ${themeColor(affair.theme)}`}>
                    {themeLabel(affair.theme)}
                  </span>
                  <span className={`badge ${
                    affair.status === 'active' ? 'bg-emerald-100 text-emerald-600 border border-emerald-200'
                    : 'bg-slate-100 text-slate-500 border border-slate-200'
                  }`}>
                    {affair.status}
                  </span>
                  <span className="badge bg-slate-100 text-slate-500 border border-slate-200">
                    {affair.affair_type}
                  </span>
                </div>

                {/* Meta */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                  <div>
                    <p className="text-slate-500">Créée</p>
                    <p className="text-slate-500">{formatDate(affair.created_at)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Dernière activité</p>
                    <p className="text-slate-500">{timeAgo(affair.last_activity || affair.created_at)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Items</p>
                    <p className="text-slate-500">{affair.item_count || 0}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Gravité</p>
                    <p className={`font-bold ${
                      affair.gravity_score >= 0.8 ? 'text-red-600' :
                      affair.gravity_score >= 0.5 ? 'text-orange-400' : 'text-emerald-600'
                    }`}>{Math.round(affair.gravity_score * 100)}%</p>
                  </div>
                </div>
              </div>

              {/* BMG Gauge large */}
              <div className="flex flex-col items-center gap-2">
                <BmgGauge value={affair.bmg || 0} size={120} label={bmg?.niveau_alerte} />
                <button
                  onClick={handleRecalculate}
                  disabled={recalculating}
                  className="text-[10px] text-teal-600 hover:text-teal-500 disabled:opacity-50"
                >
                  {recalculating ? 'Calcul...' : 'Recalculer BMG'}
                </button>
              </div>
            </div>
          </div>

          {/* ── Two column layout ─────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* ── Left: BMG Details + Entities ── */}
            <div className="lg:col-span-2 space-y-6">

              {/* BMG par canal */}
              {bmg && bmg.bnp_by_canal && (
                <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-500 mb-4">BNP par canal</h3>
                  <div className="space-y-3">
                    {Object.entries(bmg.bnp_by_canal).map(([canal, val]) => (
                      <CanalBar key={canal} canal={canal} value={val as number} max={maxCanal} />
                    ))}
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
                    <span>{bmg.active_canals} canaux actifs</span>
                    {bmg.multi_canal_bonus && (
                      <span className="text-teal-600">Bonus multi-canal actif</span>
                    )}
                    <span>Dominant: {bmg.dominant_canal || '—'}</span>
                  </div>
                </div>
              )}

              {/* BMG History */}
              {affair.bmg_history && affair.bmg_history.length > 1 && (
                <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-500 mb-4">Évolution BMG</h3>
                  <div className="flex items-end gap-1 h-24">
                    {affair.bmg_history.slice(-20).map((h, i) => {
                      const pct = Math.min(100, Math.max(5, h.bmg))
                      const color = h.bmg >= 75 ? 'bg-red-500' :
                                    h.bmg >= 50 ? 'bg-orange-500' :
                                    h.bmg >= 25 ? 'bg-amber-500' : 'bg-emerald-500'
                      return (
                        <div
                          key={i}
                          className={`flex-1 rounded-t ${color} transition-all`}
                          style={{ height: `${pct}%` }}
                          title={`BMG ${Math.round(h.bmg)} — ${new Date(h.at).toLocaleDateString('fr-FR')}`}
                        />
                      )
                    })}
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                    <span>{formatDate(affair.bmg_history[0]?.at)}</span>
                    <span>{formatDate(affair.bmg_history[affair.bmg_history.length - 1]?.at)}</span>
                  </div>
                </div>
              )}

              {/* Entités */}
              <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                <h3 className="text-sm font-semibold text-slate-500 mb-3">Entités</h3>
                <div className="space-y-4">
                  {affair.elected && affair.elected.length > 0 && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Élus</p>
                      <div className="flex flex-wrap gap-1.5">
                        {affair.elected.map((e, i) => (
                          <span key={i} className="text-xs px-2 py-1 rounded-lg bg-purple-50 text-purple-600 border border-purple-200">
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {affair.institutions && affair.institutions.length > 0 && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Institutions</p>
                      <div className="flex flex-wrap gap-1.5">
                        {affair.institutions.map((e, i) => (
                          <span key={i} className="text-xs px-2 py-1 rounded-lg bg-teal-50 text-teal-600 border border-teal-200">
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {affair.entities && affair.entities.length > 0 && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Autres entités</p>
                      <div className="flex flex-wrap gap-1.5">
                        {affair.entities.map((e, i) => (
                          <span key={i} className="text-xs px-2 py-1 rounded-lg bg-slate-100 text-slate-500">
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Sources */}
              <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                <h3 className="text-sm font-semibold text-slate-500 mb-3">Sources ({affair.sources?.length || 0})</h3>
                <div className="flex flex-wrap gap-2">
                  {(affair.sources || []).map((src, i) => (
                    <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-slate-100 text-slate-500 border border-slate-200">
                      {src}
                    </span>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-slate-200 text-xs text-slate-500">
                  {linkedArticles.length} articles, {linkedRadio.length} transcriptions radio, {linkedSocial.length} posts sociaux
                </div>
              </div>

              {/* ── Articles liés ────────────────── */}
              {linkedArticles.length > 0 && (
                <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-500 mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-teal-500" />
                    Articles ({linkedArticles.length})
                  </h3>
                  <div className="space-y-3">
                    {linkedArticles.map((art) => (
                      <div key={art._id} className="bg-slate-50 rounded-lg border border-slate-200 p-3 hover:border-slate-300 transition-colors">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            {art.url ? (
                              <a href={art.url} target="_blank" rel="noopener noreferrer"
                                className="text-sm font-medium text-teal-600 hover:text-teal-500 transition-colors line-clamp-2">
                                {art.title}
                              </a>
                            ) : (
                              <p className="text-sm font-medium text-slate-700 line-clamp-2">{art.title}</p>
                            )}
                            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-500">
                              <span className="font-medium text-slate-500">{art.source}</span>
                              {art.date && <span>{art.date}</span>}
                              {art.theme && (
                                <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">{art.theme}</span>
                              )}
                            </div>
                          </div>
                          {art.gravity_score != null && art.gravity_score > 0 && (
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                              art.gravity_score >= 0.8 ? 'bg-red-100 text-red-600'
                              : art.gravity_score >= 0.5 ? 'bg-orange-100 text-orange-400'
                              : 'bg-slate-100 text-slate-500'
                            }`}>
                              {Math.round(art.gravity_score * 100)}%
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Radio liées ──────────────────── */}
              {linkedRadio.length > 0 && (
                <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-500 mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    Transcriptions radio ({linkedRadio.length})
                  </h3>
                  <div className="space-y-3">
                    {linkedRadio.map((radio) => (
                      <div key={radio._id} className="bg-slate-50 rounded-lg border border-slate-200 p-3">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-xs font-medium text-amber-600">{radio.radio}</span>
                          {radio.captured_at && (
                            <span className="text-[10px] text-slate-500">{radio.captured_at}</span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 line-clamp-3">{radio.summary || radio.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Posts sociaux liés ───────────── */}
              {linkedSocial.length > 0 && (
                <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-500 mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-pink-500" />
                    Posts sociaux ({linkedSocial.length})
                  </h3>
                  <div className="space-y-3">
                    {linkedSocial.map((post) => (
                      <div key={post._id} className="bg-slate-50 rounded-lg border border-slate-200 p-3">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-xs font-medium text-pink-600">{post.platform}</span>
                          {post.author && <span className="text-[10px] text-slate-500">@{post.author}</span>}
                        </div>
                        <p className="text-xs text-slate-500 line-clamp-3">{post.text}</p>
                        {post.url && (
                          <a href={post.url} target="_blank" rel="noopener noreferrer"
                            className="text-[10px] text-teal-600 hover:text-teal-500 mt-1 inline-block">
                            Voir le post
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* ── Right: Timeline ────────────── */}
            <div>
              <div className="bg-white shadow-sm rounded-xl border border-slate-200 p-5 sticky top-8">
                <h3 className="text-sm font-semibold text-slate-500 mb-4">Chronologie</h3>
                {timeline.length === 0 ? (
                  <p className="text-xs text-slate-500">Aucun événement</p>
                ) : (
                  <div className="max-h-[500px] overflow-y-auto pr-1">
                    {timeline.slice(0, 30).map((evt) => (
                      <TimelineItem key={evt._id} event={evt} />
                    ))}
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      </main>
    </div>
  )
}
