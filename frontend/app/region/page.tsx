'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import { fetchAffairsByInstitution, type CompetenceGroup } from '../../lib/api'

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

export default function RegionPage() {
  const [groups, setGroups] = useState<Record<string, CompetenceGroup>>({})
  const [totalMatched, setTotalMatched] = useState(0)
  const [loading, setLoading] = useState(true)
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      const res = await fetchAffairsByInstitution('region')
      setGroups(res.groups || {})
      setTotalMatched(res.total_matched || 0)
      const top = Object.entries(res.groups || {}).sort(([, a], [, b]) => b.count - a.count)[0]
      if (top && top[1].count > 0) setOpenGroup(top[0])
    } catch (e) {
      console.error('Region load error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const toggleGroup = (name: string) => {
    setOpenGroup(prev => prev === name ? null : name)
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-main)' }}>
      <Sidebar />
      <main className="ml-64 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Région Guadeloupe
            </h1>
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Affaires regroupées par compétences régionales — {totalMatched} affaires classées
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(groups).map(([name, group]) => {
                const isOpen = openGroup === name
                return (
                  <div key={name} className="glass-card border border-[rgba(255,255,255,0.08)] overflow-hidden">
                    <button
                      onClick={() => toggleGroup(name)}
                      className="w-full flex items-center gap-3 p-4 text-left hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ background: group.color, boxShadow: `0 0 8px ${group.color}40` }} />
                      <span className="text-sm font-semibold text-white flex-1">{name}</span>

                      {group.count > 0 && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
                          style={{ background: `${group.color}20`, color: group.color }}>
                          {group.count} affaire{group.count > 1 ? 's' : ''}
                        </span>
                      )}
                      {group.max_gravity > 0 && (
                        <span className={`text-[10px] font-bold ${
                          group.max_gravity >= 0.7 ? 'text-red-400'
                          : group.max_gravity >= 0.5 ? 'text-orange-400'
                          : 'text-emerald-400'
                        }`}>
                          max {Math.round(group.max_gravity * 100)}%
                        </span>
                      )}

                      <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                        fill="none" stroke="rgba(255,255,255,0.3)" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>

                    {isOpen && (
                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                        {group.affairs.length === 0 ? (
                          <p className="text-xs py-6 text-center" style={{ color: 'rgba(255,255,255,0.25)' }}>
                            Aucune affaire dans cette compétence pour le moment
                          </p>
                        ) : (
                          <div>
                            {group.affairs.map((affair, idx) => (
                              <Link key={`${affair._id}-${idx}`} href={`/affairs/${affair._id}`}>
                                <div
                                  className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.03] transition-colors cursor-pointer"
                                  style={{
                                    borderBottom: idx < group.affairs.length - 1
                                      ? '1px solid rgba(255,255,255,0.04)' : 'none',
                                  }}
                                >
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold flex-shrink-0 ${
                                    affair.gravity_score >= 0.7 ? 'bg-red-500/20 text-red-400'
                                    : affair.gravity_score >= 0.5 ? 'bg-orange-500/20 text-orange-400'
                                    : affair.gravity_score >= 0.3 ? 'bg-yellow-500/20 text-yellow-400'
                                    : 'bg-emerald-500/20 text-emerald-400'
                                  }`}>
                                    {Math.round(affair.gravity_score * 100)}%
                                  </span>

                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-white truncate">{affair.title}</p>
                                    {affair.description && (
                                      <p className="text-[10px] truncate mt-0.5"
                                        style={{ color: 'rgba(255,255,255,0.3)' }}>
                                        {affair.description}
                                      </p>
                                    )}
                                  </div>

                                  {affair.sentiment && affair.sentiment !== 'neutre' && (
                                    <span className="text-[10px] flex-shrink-0" style={{
                                      color: affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif')
                                        ? '#f87171' : affair.sentiment.includes('positif') ? '#6ee7b7' : '#fbbf24'
                                    }}>
                                      {affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif')
                                        ? '😠' : affair.sentiment.includes('positif') ? '😊' : '😐'}
                                    </span>
                                  )}

                                  {affair.communes && affair.communes.length > 0 && (
                                    <span className="text-[9px] px-1.5 py-0.5 rounded-full flex-shrink-0"
                                      style={{
                                        background: 'rgba(99,102,241,0.1)',
                                        color: '#a5b4fc',
                                        border: '1px solid rgba(99,102,241,0.2)',
                                      }}>
                                      {affair.communes[0]}
                                      {affair.communes.length > 1 && ` +${affair.communes.length - 1}`}
                                    </span>
                                  )}

                                  <span className="text-[9px] flex-shrink-0"
                                    style={{ color: 'rgba(255,255,255,0.2)' }}>
                                    {affair.item_count || 0} items · {timeAgo(affair.last_activity || affair.created_at || '')}
                                  </span>
                                </div>
                              </Link>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
