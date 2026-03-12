'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import GuadeloupeMap from '../../components/GuadeloupeMap'
import BmgGauge from '../../components/BmgGauge'
import { type Affair } from '../../lib/api'

const API = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

interface CommuneInfo {
  count: number
  maxGravity: number
  affairs: Array<{
    _id: string
    title: string
    gravity_score: number
    sentiment: string
    theme: string
  }>
}

interface ElectionAffair extends Affair {
  communes?: string[]
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

function sentimentEmoji(s: string): string {
  if (!s || s === 'neutre') return ''
  if (s.includes('négatif') || s.includes('negatif') || s === 'critique') return '😠'
  if (s.includes('positif')) return '😊'
  return '😐'
}

function sentimentColor(s: string): string {
  if (!s || s === 'neutre') return 'rgba(255,255,255,0.35)'
  if (s.includes('négatif') || s.includes('negatif') || s === 'critique') return '#f87171'
  if (s.includes('positif')) return '#6ee7b7'
  return '#fbbf24'
}

export default function ElectionsPage() {
  const [communeData, setCommuneData] = useState<Record<string, CommuneInfo>>({})
  const [elections, setElections] = useState<ElectionAffair[]>([])
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const [mapRes, elecRes] = await Promise.all([
        fetch(`${API}/api/affairs/by-commune`).then(r => r.json()),
        fetch(`${API}/api/affairs/elections`).then(r => r.json()),
      ])
      setCommuneData(mapRes.communes || {})
      setElections(elecRes.affairs || [])
    } catch (e) {
      console.error('Elections load error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleCommuneClick = (commune: string) => {
    setSelectedCommune(prev => prev === commune ? null : commune)
  }

  const communeAffairs = selectedCommune
    ? communeData[selectedCommune]?.affairs || []
    : []

  const mapData: Record<string, { count: number; maxGravity: number }> = {}
  for (const [name, info] of Object.entries(communeData)) {
    mapData[name] = { count: info.count, maxGravity: info.maxGravity }
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-main)' }}>
      <Sidebar />
      <main className="ml-64 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Elections Municipales 2026
            </h1>
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Carte des affaires par commune + suivi des sujets électoraux
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

              {/* Carte — prend 2 colonnes */}
              <div className="xl:col-span-2">
                <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5">
                  <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/30" />
                    Carte des affaires par commune
                  </h2>
                  <GuadeloupeMap
                    communeData={mapData}
                    onCommuneClick={handleCommuneClick}
                  />

                  {/* Détail commune sélectionnée */}
                  {selectedCommune && (
                    <div className="mt-4 p-4 rounded-xl" style={{
                      background: 'rgba(99,102,241,0.08)',
                      border: '1px solid rgba(99,102,241,0.2)',
                    }}>
                      <h3 className="text-sm font-semibold text-white mb-3">
                        {selectedCommune} — {communeAffairs.length} affaire{communeAffairs.length > 1 ? 's' : ''}
                      </h3>
                      {communeAffairs.length === 0 ? (
                        <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
                          Aucune affaire active dans cette commune
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {communeAffairs.map((a) => (
                            <Link key={a._id} href={`/affairs/${a._id}`}>
                              <div className="flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors hover:bg-white/5">
                                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                                  a.gravity_score >= 0.7 ? 'bg-red-500/20 text-red-400'
                                  : a.gravity_score >= 0.5 ? 'bg-orange-500/20 text-orange-400'
                                  : 'bg-emerald-500/20 text-emerald-400'
                                }`}>
                                  {Math.round(a.gravity_score * 100)}%
                                </span>
                                <span className="text-xs text-white truncate flex-1">{a.title}</span>
                                {a.sentiment && a.sentiment !== 'neutre' && (
                                  <span className="text-[10px]" style={{ color: sentimentColor(a.sentiment) }}>
                                    {sentimentEmoji(a.sentiment)}
                                  </span>
                                )}
                              </div>
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Stats communes */}
                <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5 mt-4">
                  <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-500 shadow-lg shadow-amber-500/30" />
                    Communes les plus actives
                  </h2>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                    {Object.entries(communeData)
                      .sort(([, a], [, b]) => b.count - a.count)
                      .slice(0, 12)
                      .map(([commune, info]) => (
                        <button
                          key={commune}
                          onClick={() => handleCommuneClick(commune)}
                          className={`p-3 rounded-lg text-left transition-all ${
                            selectedCommune === commune ? 'ring-1 ring-indigo-500' : ''
                          }`}
                          style={{
                            background: selectedCommune === commune
                              ? 'rgba(99,102,241,0.15)'
                              : 'rgba(255,255,255,0.03)',
                            border: '1px solid rgba(255,255,255,0.06)',
                          }}
                        >
                          <p className="text-xs font-medium text-white truncate">{commune}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
                              {info.count} affaire{info.count > 1 ? 's' : ''}
                            </span>
                            <span className={`text-[10px] font-bold ${
                              info.maxGravity >= 0.7 ? 'text-red-400'
                              : info.maxGravity >= 0.5 ? 'text-orange-400'
                              : 'text-emerald-400'
                            }`}>
                              {Math.round(info.maxGravity * 100)}%
                            </span>
                          </div>
                        </button>
                      ))}
                  </div>
                </div>
              </div>

              {/* Colonne droite : affaires électorales */}
              <div>
                <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5">
                  <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-500 shadow-lg shadow-purple-500/30" />
                    Affaires Electorales ({elections.length})
                  </h2>
                  {elections.length === 0 ? (
                    <p className="text-xs py-8 text-center" style={{ color: 'rgba(255,255,255,0.3)' }}>
                      Aucune affaire électorale détectée pour le moment.
                      Les articles sur les municipales 2026 créeront automatiquement des affaires.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {elections.map((affair) => (
                        <Link key={affair._id} href={`/affairs/${affair._id}`}>
                          <div className="glass-card-static rounded-lg border border-[rgba(255,255,255,0.06)] p-3 cursor-pointer hover:border-[rgba(255,255,255,0.15)] transition-all">
                            <div className="flex items-start gap-2 mb-2">
                              <div className="flex-1 min-w-0">
                                <h3 className="text-xs font-semibold text-white line-clamp-2">
                                  {affair.title}
                                </h3>
                              </div>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold flex-shrink-0 ${
                                affair.gravity_score >= 0.7 ? 'bg-red-500/20 text-red-400'
                                : affair.gravity_score >= 0.5 ? 'bg-orange-500/20 text-orange-400'
                                : 'bg-emerald-500/20 text-emerald-400'
                              }`}>
                                {Math.round(affair.gravity_score * 100)}%
                              </span>
                            </div>

                            {affair.description && (
                              <p className="text-[10px] line-clamp-2 mb-2" style={{ color: 'rgba(255,255,255,0.4)' }}>
                                {affair.description}
                              </p>
                            )}

                            <div className="flex items-center gap-2 flex-wrap">
                              {affair.communes && affair.communes.length > 0 && affair.communes.slice(0, 2).map((c) => (
                                <span key={c} className="text-[9px] px-1.5 py-0.5 rounded-full"
                                  style={{
                                    background: 'rgba(99,102,241,0.15)',
                                    color: '#a5b4fc',
                                    border: '1px solid rgba(99,102,241,0.3)',
                                  }}>
                                  {c}
                                </span>
                              ))}
                              {affair.sentiment && affair.sentiment !== 'neutre' && (
                                <span className="text-[9px]" style={{ color: sentimentColor(affair.sentiment) }}>
                                  {sentimentEmoji(affair.sentiment)} {affair.sentiment}
                                </span>
                              )}
                              <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                                {affair.item_count} items
                              </span>
                              <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                                {timeAgo(affair.last_activity || affair.created_at)}
                              </span>
                            </div>
                          </div>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>

                {/* Conseillers départementaux — résumé */}
                <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5 mt-4">
                  <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-teal-500 shadow-lg shadow-teal-500/30" />
                    Conseil Départemental
                  </h2>
                  <p className="text-xs mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    42 conseillers — 21 cantons — Mandature 2021-2028
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { name: 'Guy Losbar', role: 'Président', canton: 'Baie-Mahault 2' },
                      { name: 'Elie Califer', role: 'Conseiller', canton: 'Basse-Terre' },
                      { name: 'Henry Angélique', role: 'Conseiller', canton: 'Pointe-à-Pitre' },
                      { name: 'Tania Galvani', role: 'Conseillère', canton: 'Pointe-à-Pitre' },
                      { name: 'Catherine Joab', role: 'Conseillère', canton: 'Gosier' },
                      { name: 'Daniel Dulac', role: 'Conseiller', canton: 'Le Moule' },
                      { name: 'Gabrielle Louis-Carabin', role: 'Conseillère', canton: 'Le Moule' },
                      { name: 'Jean Dartron', role: 'Conseiller', canton: "Morne-à-l'Eau" },
                      { name: 'Maryse Etzol', role: 'Conseillère', canton: 'Marie-Galante' },
                      { name: 'Jimmy Fausta', role: 'Conseiller', canton: 'Trois-Rivières' },
                      { name: 'Jean-Philippe Courtois', role: 'Conseiller', canton: 'Capesterre-B-E' },
                      { name: 'Michel Mado', role: 'Conseiller', canton: 'Baie-Mahault' },
                    ].map((c) => (
                      <div key={c.name} className="flex items-center gap-2 text-[10px]">
                        <span className="text-white font-medium flex-1">{c.name}</span>
                        <span style={{ color: 'rgba(255,255,255,0.3)' }}>{c.canton}</span>
                      </div>
                    ))}
                    <p className="text-[10px] pt-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
                      + 30 autres conseillers suivis automatiquement
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
