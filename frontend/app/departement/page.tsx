'use client'

import { useState } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'

/* ─── Données conseillers départementaux ─── */
const CONSEILLERS = [
  { name: 'Guy Losbar', role: 'Président', canton: 'Baie-Mahault 2', parti: 'GUSR' },
  { name: 'Josette Borel-Lincertin', role: '1ère VP', canton: 'Petit-Bourg 1', parti: '' },
  { name: 'Elie Califer', role: 'Conseiller', canton: 'Basse-Terre', parti: 'PS' },
  { name: 'Henry Angélique', role: 'Conseiller', canton: 'Pointe-à-Pitre 1', parti: '' },
  { name: 'Tania Galvani', role: 'Conseillère', canton: 'Pointe-à-Pitre 1', parti: '' },
  { name: 'Catherine Joab', role: 'Conseillère', canton: 'Gosier', parti: '' },
  { name: 'Daniel Dulac', role: 'Conseiller', canton: 'Le Moule', parti: '' },
  { name: 'Gabrielle Louis-Carabin', role: 'Conseillère', canton: 'Le Moule', parti: '' },
  { name: 'Jean Dartron', role: 'Conseiller', canton: "Morne-à-l'Eau", parti: '' },
  { name: 'Maryse Etzol', role: 'Conseillère', canton: 'Marie-Galante', parti: '' },
  { name: 'Jimmy Fausta', role: 'Conseiller', canton: 'Trois-Rivières', parti: '' },
  { name: 'Jean-Philippe Courtois', role: 'Conseiller', canton: 'Capesterre-B-E 2', parti: '' },
  { name: 'Michel Mado', role: 'Conseiller', canton: 'Baie-Mahault 1', parti: '' },
  { name: 'Marylène Adhel', role: 'Conseillère', canton: 'Sainte-Rose', parti: '' },
  { name: 'Louis Galantine', role: 'Conseiller', canton: 'Sainte-Rose', parti: '' },
  { name: 'Francesca Faithful', role: 'Conseillère', canton: 'Les Abymes 2', parti: '' },
  { name: 'Cédric Cornet', role: 'Conseiller', canton: 'Les Abymes 1', parti: '' },
  { name: 'Sylvie Mérion', role: 'Conseillère', canton: 'Les Abymes 1', parti: '' },
  { name: 'Jeanny Marc', role: 'Conseillère', canton: 'Deshaies', parti: '' },
  { name: 'Ferdy Louisy', role: 'Conseiller', canton: 'Goyave', parti: '' },
  { name: 'Marie-Luce Penchard', role: 'Conseillère', canton: 'Petit-Bourg 2', parti: '' },
  { name: 'Max Mathiasin', role: 'Conseiller', canton: 'Saint-François', parti: '' },
  { name: 'Christian Baptiste', role: 'Conseiller', canton: 'Lamentin', parti: '' },
  { name: 'Justine Bénin', role: 'Conseillère', canton: 'Sainte-Anne', parti: '' },
]

/* ─── Structures départementales ─── */
const STRUCTURES = [
  {
    cat: 'Social & Solidarité',
    color: '#818cf8',
    items: [
      { name: 'ASE', full: "Aide Sociale à l'Enfance" },
      { name: 'PMI', full: 'Protection Maternelle et Infantile' },
      { name: 'MDPH', full: 'Maison des Personnes Handicapées' },
      { name: 'MDA', full: "Maison de l'Autonomie" },
      { name: 'DICS', full: 'Insertion et Cohésion Sociale' },
      { name: 'Foyer de l\'Enfance', full: "Foyer Départemental de l'Enfance" },
      { name: 'CNAS', full: 'Caisse Nationale d\'Action Sociale' },
    ],
  },
  {
    cat: 'Sécurité',
    color: '#f87171',
    items: [
      { name: 'SDIS 971', full: 'Service d\'Incendie et de Secours' },
    ],
  },
  {
    cat: 'Santé',
    color: '#34d399',
    items: [
      { name: 'EPSM', full: 'Établissement Public de Santé Mentale' },
      { name: 'CHU', full: 'Centre Hospitalier Universitaire' },
      { name: 'LDA', full: "Laboratoire Départemental d'Analyses" },
    ],
  },
  {
    cat: 'Éducation & Culture',
    color: '#c084fc',
    items: [
      { name: 'Collèges', full: '42 collèges publics' },
      { name: 'Bibliothèque Départementale', full: 'Réseau de lecture publique' },
      { name: 'Archives Départementales', full: 'Conservation du patrimoine' },
    ],
  },
  {
    cat: 'Aménagement & Infrastructure',
    color: '#fbbf24',
    items: [
      { name: 'Routes Départementales', full: 'Voirie et ouvrages d\'art' },
      { name: 'EPFAG', full: 'Établissement Public Foncier' },
      { name: 'Port Autonome', full: 'Port Autonome de la Guadeloupe' },
      { name: 'SIG 971', full: 'Système d\'Information Géographique' },
    ],
  },
  {
    cat: 'Intercommunalités',
    color: '#22d3ee',
    items: [
      { name: 'Cap Excellence', full: 'Abymes, Pointe-à-Pitre, Baie-Mahault' },
      { name: 'CARL', full: 'Communauté d\'Agglomération Riviera du Levant' },
      { name: 'CANGT', full: 'Communauté d\'Agglomération Nord Grande-Terre' },
      { name: 'Grand Sud Caraïbe', full: 'Basse-Terre et sud' },
      { name: 'CC Marie-Galante', full: 'Grand-Bourg, Capesterre, Saint-Louis' },
    ],
  },
]

export default function DepartementPage() {
  const [activeTab, setActiveTab] = useState<'conseillers' | 'structures'>('conseillers')
  const [searchTerm, setSearchTerm] = useState('')

  const filteredConseillers = CONSEILLERS.filter((c) =>
    c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.canton.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-main)' }}>
      <Sidebar />
      <main className="ml-64 flex-1 p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Département de la Guadeloupe
            </h1>
            <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Conseil départemental — 42 conseillers · 21 cantons · Mandature 2021-2028
            </p>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1 mb-6 p-1 rounded-xl w-fit"
            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            {(['conseillers', 'structures'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="px-4 py-2 rounded-lg text-xs font-medium transition-all"
                style={activeTab === tab ? {
                  background: 'rgba(99,102,241,0.15)',
                  color: '#a5b4fc',
                  border: '1px solid rgba(99,102,241,0.3)',
                } : {
                  color: 'rgba(255,255,255,0.4)',
                }}
              >
                {tab === 'conseillers' ? '👥 Conseillers' : '🏛️ Structures'}
              </button>
            ))}
          </div>

          {/* ─── CONSEILLERS ─── */}
          {activeTab === 'conseillers' && (
            <div>
              {/* Recherche */}
              <div className="mb-4">
                <input
                  type="text"
                  placeholder="Rechercher un conseiller ou canton..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full max-w-sm px-4 py-2 rounded-xl text-xs text-white placeholder-white/25 outline-none"
                  style={{
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}
                />
              </div>

              {/* Président en vedette */}
              <div className="glass-card border border-[rgba(255,255,255,0.08)] p-5 mb-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center"
                    style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 15px rgba(99,102,241,0.3)' }}>
                    <span className="text-lg font-bold text-white">GL</span>
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Guy Losbar</h2>
                    <p className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                      Président du Conseil Départemental · Canton de Baie-Mahault 2 · GUSR
                    </p>
                  </div>
                </div>
              </div>

              {/* Grille conseillers */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {filteredConseillers
                  .filter((c) => c.name !== 'Guy Losbar')
                  .map((c) => (
                    <div key={c.name} className="glass-card-static p-4 flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)' }}>
                        <span className="text-[10px] font-bold" style={{ color: '#a5b4fc' }}>
                          {c.name.split(' ').map(n => n[0]).join('')}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-white truncate">{c.name}</p>
                        <p className="text-[10px] truncate" style={{ color: 'rgba(255,255,255,0.3)' }}>
                          {c.role} · {c.canton}
                        </p>
                      </div>
                    </div>
                  ))}
              </div>

              {filteredConseillers.length === 0 && (
                <p className="text-xs py-8 text-center" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  Aucun résultat pour « {searchTerm} »
                </p>
              )}
            </div>
          )}

          {/* ─── STRUCTURES ─── */}
          {activeTab === 'structures' && (
            <div className="space-y-4">
              {STRUCTURES.map((group) => (
                <div key={group.cat} className="glass-card border border-[rgba(255,255,255,0.08)] p-5">
                  <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: group.color, boxShadow: `0 0 8px ${group.color}40` }} />
                    {group.cat}
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {group.items.map((item) => (
                      <div key={item.name} className="glass-card-static p-3 rounded-lg">
                        <p className="text-xs font-medium text-white">{item.name}</p>
                        <p className="text-[10px] mt-0.5" style={{ color: 'rgba(255,255,255,0.35)' }}>{item.full}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <p className="text-[10px] text-center py-2" style={{ color: 'rgba(255,255,255,0.2)' }}>
                Toutes ces structures sont suivies automatiquement par la veille
              </p>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
