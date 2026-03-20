'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { fetchSharedAffair, type AffairContext } from '../../../lib/api'

const themeLabels: Record<string, string> = {
  securite_justice: 'Sécurité / Justice',
  politique: 'Politique',
  economie_emploi: 'Économie / Emploi',
  sante_social: 'Santé / Social',
  education: 'Éducation',
  culture_patrimoine: 'Culture / Patrimoine',
  eau_env: 'Eau / Environnement',
  energie_transports: 'Énergie / Transports',
  sport: 'Sport',
  general: 'Général',
}

const sentimentIcon = (s: string) => {
  if (s?.includes('négatif')) return '🔴'
  if (s?.includes('positif')) return '🟢'
  if (s === 'mitigé') return '🟡'
  return '⚪'
}

export default function SharedAffairPage() {
  const params = useParams()
  const token = params?.token as string

  const [data, setData] = useState<Awaited<ReturnType<typeof fetchSharedAffair>> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    fetchSharedAffair(token)
      .then(setData)
      .catch(() => setError('Lien invalide ou expiré'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-slate-400 text-lg animate-pulse">Chargement...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="bg-slate-900 border border-red-500/30 rounded-2xl p-8 max-w-md text-center">
          <div className="text-4xl mb-4">🔒</div>
          <h1 className="text-xl font-bold text-white mb-2">Lien invalide</h1>
          <p className="text-slate-400">Ce lien de consultation n&apos;existe pas ou a été révoqué.</p>
        </div>
      </div>
    )
  }

  const { affair, ai_context, articles } = data

  const gravityPct = Math.round(affair.gravity_score * 100)
  const bmgPct = Math.round(affair.bmg * 100)

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-emerald-900/40 to-slate-900 border-b border-emerald-500/20 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <span className="text-2xl">📊</span>
          <div>
            <h1 className="text-sm font-semibold text-emerald-400 tracking-wider uppercase">Veille Média Guadeloupe</h1>
            <p className="text-xs text-slate-400">Consultation publique</p>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Titre + infos principales */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-start gap-4">
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-white mb-2">{affair.title}</h2>
              {affair.description && (
                <p className="text-slate-400 text-sm mb-4">{affair.description}</p>
              )}
              <div className="flex flex-wrap gap-2">
                <span className="px-2 py-1 rounded-full text-xs bg-slate-800 text-slate-300 border border-slate-700">
                  {themeLabels[affair.theme] || affair.theme}
                </span>
                <span className="px-2 py-1 rounded-full text-xs bg-slate-800 text-slate-300 border border-slate-700">
                  {affair.item_count} sources
                </span>
                <span className="px-2 py-1 rounded-full text-xs bg-slate-800 text-slate-300 border border-slate-700">
                  {sentimentIcon(affair.sentiment)} {affair.sentiment}
                </span>
              </div>
            </div>
            {/* Jauges */}
            <div className="flex gap-6 flex-shrink-0">
              <div className="text-center">
                <div className={`text-3xl font-black ${gravityPct >= 70 ? 'text-red-400' : gravityPct >= 40 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {gravityPct}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider">Gravité</div>
              </div>
              <div className="text-center">
                <div className={`text-3xl font-black ${bmgPct >= 70 ? 'text-red-400' : bmgPct >= 40 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {bmgPct}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider">Bruit</div>
              </div>
            </div>
          </div>

          {/* Élus et institutions */}
          {(affair.elected?.length > 0 || affair.institutions?.length > 0) && (
            <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap gap-2">
              {affair.elected?.map(e => (
                <span key={e} className="px-2 py-0.5 rounded text-xs bg-purple-500/10 text-purple-300 border border-purple-500/20">{e}</span>
              ))}
              {affair.institutions?.map(i => (
                <span key={i} className="px-2 py-0.5 rounded text-xs bg-blue-500/10 text-blue-300 border border-blue-500/20">{i}</span>
              ))}
            </div>
          )}
        </div>

        {/* Contexte IA */}
        {ai_context && (
          <div className="bg-slate-900/80 border border-purple-500/20 rounded-2xl p-6">
            <h3 className="text-lg font-bold text-purple-400 mb-3 flex items-center gap-2">
              <span>🧠</span> Analyse IA
            </h3>
            <p className="text-slate-300 text-sm leading-relaxed mb-4">{ai_context.contexte}</p>

            {ai_context.enjeux && ai_context.enjeux.length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Enjeux</h4>
                <div className="space-y-1">
                  {ai_context.enjeux.map((e: string, i: number) => (
                    <div key={i} className="text-sm text-slate-400 flex items-start gap-2">
                      <span className="text-purple-400 mt-0.5">•</span> {e}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {ai_context.historique && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Historique</h4>
                <p className="text-sm text-slate-400">{ai_context.historique}</p>
              </div>
            )}

            {ai_context.impact_potentiel && (
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Impact potentiel</h4>
                <p className="text-sm text-slate-400">{ai_context.impact_potentiel}</p>
              </div>
            )}

            {ai_context.mots_cles_contexte && ai_context.mots_cles_contexte.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-800 flex flex-wrap gap-1">
                {ai_context.mots_cles_contexte.map((k: string, i: number) => (
                  <span key={i} className="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-400 border border-slate-700">{k}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Articles liés */}
        {articles.length > 0 && (
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-lg font-bold text-white mb-3 flex items-center gap-2">
              <span>📰</span> Articles liés
              <span className="text-xs text-slate-500 font-normal ml-2">({data.total_articles} au total)</span>
            </h3>
            <div className="space-y-2">
              {articles.map(art => (
                <div key={art._id} className="flex items-center gap-3 py-2 border-b border-slate-800/50 last:border-0">
                  <div className={`text-xs font-bold w-8 text-center ${
                    art.gravity_score >= 0.6 ? 'text-red-400' : art.gravity_score >= 0.4 ? 'text-amber-400' : 'text-slate-500'
                  }`}>
                    {Math.round(art.gravity_score * 100)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{art.title}</div>
                    <div className="text-[10px] text-slate-500">{art.source} · {themeLabels[art.theme] || art.theme}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="text-center text-xs text-slate-600 py-6">
          Veille Média Guadeloupe — Consultation en lecture seule
        </div>
      </div>
    </div>
  )
}
