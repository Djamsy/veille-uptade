'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from './Sidebar'
import { fetchAffairsByInstitution, type CompetenceGroup } from '../lib/api'
import { timeAgo, gravityClass, sentimentColor, sentimentEmoji } from '../lib/formatters'

interface Props {
  institution: 'departement' | 'region'
  title: string
  subtitle: string
}

export default function InstitutionPage({ institution, title, subtitle }: Props) {
  const [groups, setGroups] = useState<Record<string, CompetenceGroup>>({})
  const [totalMatched, setTotalMatched] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const loadData = useCallback(async () => {
    try {
      setError('')
      const res = await fetchAffairsByInstitution(institution)
      setGroups(res.groups || {})
      setTotalMatched(res.total_matched || 0)
      const top = Object.entries(res.groups || {}).sort(([, a], [, b]) => b.count - a.count)[0]
      if (top && top[1].count > 0) setOpenGroup(top[0])
    } catch (e) {
      console.error(`${institution} load error:`, e)
      setError('Erreur de connexion au serveur')
    } finally {
      setLoading(false)
    }
  }, [institution])

  useEffect(() => { loadData() }, [loadData])

  const toggleGroup = (name: string) => {
    setOpenGroup(prev => prev === name ? null : name)
  }

  // Filtrer les affaires par recherche
  const filterAffairs = (affairs: CompetenceGroup['affairs']) => {
    if (!searchQuery.trim()) return affairs
    const q = searchQuery.toLowerCase()
    return affairs.filter(a =>
      a.title.toLowerCase().includes(q) ||
      (a.description || '').toLowerCase().includes(q) ||
      (a.elected || []).some(e => e.toLowerCase().includes(q)) ||
      (a.institutions || []).some(i => i.toLowerCase().includes(q))
    )
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-main)' }}>
      <Sidebar />
      <main className="ml-0 lg:ml-60 flex-1 p-4 lg:p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">
              {title}
            </h1>
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              {subtitle} — {totalMatched} affaires classées
            </p>
          </div>

          {/* Barre de recherche */}
          <div className="mb-4">
            <div className="relative max-w-md">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" fill="none"
                stroke="rgba(255,255,255,0.3)" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Rechercher une affaire, un élu, une institution..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl text-xs text-white placeholder:text-white/25
                  focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all"
                style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Error state */}
          {error && (
            <div className="mb-4 p-4 rounded-xl flex items-center justify-between"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <span className="text-xs text-red-400">{error}</span>
              <button onClick={() => { setLoading(true); loadData() }}
                className="text-xs text-red-300 hover:text-white px-3 py-1 rounded-lg"
                style={{ background: 'rgba(239,68,68,0.15)' }}>
                Réessayer
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(groups).map(([name, group]) => {
                const isOpen = openGroup === name
                const filteredAffairs = filterAffairs(group.affairs)
                const hasResults = !searchQuery || filteredAffairs.length > 0

                if (searchQuery && !hasResults) return null

                return (
                  <div key={name} className="glass-card border border-[rgba(255,255,255,0.08)] overflow-hidden">
                    {/* Header compétence */}
                    <button
                      onClick={() => toggleGroup(name)}
                      className="w-full flex items-center gap-2 lg:gap-3 p-3 lg:p-4 text-left hover:bg-white/[0.02] transition-colors"
                      aria-expanded={isOpen}
                      aria-label={`${name}: ${group.count} affaires`}
                    >
                      <div className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ background: group.color, boxShadow: `0 0 8px ${group.color}40` }} />
                      <span className="text-xs lg:text-sm font-semibold text-white flex-1">{name}</span>

                      {group.count > 0 && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
                          style={{ background: `${group.color}20`, color: group.color }}>
                          {searchQuery ? `${filteredAffairs.length}/` : ''}{group.count}
                        </span>
                      )}
                      {group.max_gravity > 0 && (
                        <span className={`text-[10px] font-bold hidden sm:inline ${
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

                    {/* Affaires de la compétence */}
                    {isOpen && (
                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                        {filteredAffairs.length === 0 ? (
                          <p className="text-xs py-6 text-center" style={{ color: 'rgba(255,255,255,0.25)' }}>
                            {searchQuery ? 'Aucun résultat pour cette recherche' : 'Aucune affaire dans cette compétence'}
                          </p>
                        ) : (
                          <div>
                            {filteredAffairs.map((affair, idx) => (
                              <Link key={`${affair._id}-${idx}`} href={`/affairs/${affair._id}`}>
                                <div
                                  className="flex items-center gap-2 lg:gap-3 px-3 lg:px-5 py-3 hover:bg-white/[0.03] transition-colors cursor-pointer"
                                  style={{
                                    borderBottom: idx < filteredAffairs.length - 1
                                      ? '1px solid rgba(255,255,255,0.04)' : 'none',
                                  }}
                                >
                                  {/* Gravité */}
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold flex-shrink-0 ${gravityClass(affair.gravity_score)}`}>
                                    {Math.round(affair.gravity_score * 100)}%
                                  </span>

                                  {/* Titre + description */}
                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-white truncate">{affair.title}</p>
                                    {affair.description && (
                                      <p className="text-[10px] truncate mt-0.5"
                                        style={{ color: 'rgba(255,255,255,0.3)' }}>
                                        {affair.description}
                                      </p>
                                    )}
                                  </div>

                                  {/* Sentiment */}
                                  {affair.sentiment && affair.sentiment !== 'neutre' && (
                                    <span className="text-[10px] flex-shrink-0"
                                      style={{ color: sentimentColor(affair.sentiment) }}>
                                      {sentimentEmoji(affair.sentiment)}
                                    </span>
                                  )}

                                  {/* Communes (hidden on mobile) */}
                                  {affair.communes && affair.communes.length > 0 && (
                                    <span className="text-[9px] px-1.5 py-0.5 rounded-full flex-shrink-0 hidden md:inline-block"
                                      style={{
                                        background: 'rgba(99,102,241,0.1)',
                                        color: '#a5b4fc',
                                        border: '1px solid rgba(99,102,241,0.2)',
                                      }}>
                                      {affair.communes[0]}
                                      {affair.communes.length > 1 && ` +${affair.communes.length - 1}`}
                                    </span>
                                  )}

                                  {/* Items + date */}
                                  <span className="text-[9px] flex-shrink-0 hidden sm:inline"
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
