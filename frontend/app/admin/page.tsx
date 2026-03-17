'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import { useAuth } from '../../components/AuthGuard'
import {
  fetchActiveAffairsSummary,
  fetchOrphanArticles,
  fetchAffairDetail,
  mergeAffairs,
  splitAffair,
  linkArticleToAffair,
  unlinkArticleFromAffair,
  reclassifyAffair,
  archiveAffair,
  fetchAdminActivityLog,
  fetchUsers,
  updateUserRole,
  type Affair,
  type OrphanArticleAdmin,
  type AffairDetailResponse,
} from '../../lib/api'

// ── Types ──────────────────────────────────────────
interface User {
  id: string
  email: string
  name: string
  role: string
}

type Tab = 'affairs' | 'orphans' | 'users' | 'log'

// ── Helpers ────────────────────────────────────────
const priorityBadge = (p?: string) => {
  if (p === 'hot') return 'bg-red-500/20 text-red-300 border-red-500/30'
  if (p === 'watch') return 'bg-amber-500/20 text-amber-300 border-amber-500/30'
  return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
}

const gravityColor = (g: number) => {
  if (g >= 0.75) return 'text-red-400'
  if (g >= 0.55) return 'text-amber-400'
  if (g >= 0.35) return 'text-blue-400'
  return 'text-slate-400'
}

const timeAgo = (iso: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const h = Math.floor((now.getTime() - d.getTime()) / 3600000)
  if (h < 1) return 'il y a < 1h'
  if (h < 24) return `il y a ${h}h`
  const days = Math.floor(h / 24)
  return `il y a ${days}j`
}

// ══════════════════════════════════════════════════════
//  PAGE ADMIN
// ══════════════════════════════════════════════════════
export default function AdminPage() {
  const { user: authUser } = useAuth()
  const [user, setUser] = useState<User | null>(null)
  const [authError, setAuthError] = useState('')
  const [tab, setTab] = useState<Tab>('affairs')

  // Data
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [orphans, setOrphans] = useState<OrphanArticleAdmin[]>([])
  const [users, setUsers] = useState<Array<{ _id: string; email: string; name: string; role: string; created_at: string }>>([])
  const [activityLog, setActivityLog] = useState<Array<{ _id: string; affair_id: string; event: string; details: Record<string, unknown>; timestamp: string }>>([])
  const [loading, setLoading] = useState(true)
  const [actionMsg, setActionMsg] = useState('')

  // Selection
  const [selectedAffairs, setSelectedAffairs] = useState<Set<string>>(new Set())
  const [selectedOrphan, setSelectedOrphan] = useState<string | null>(null)
  const [expandedAffair, setExpandedAffair] = useState<string | null>(null)
  const [affairDetail, setAffairDetail] = useState<AffairDetailResponse | null>(null)

  // Edit modal
  const [editingAffair, setEditingAffair] = useState<Affair | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editTheme, setEditTheme] = useState('')
  const [editPriority, setEditPriority] = useState('')

  // ── Auth from context (AuthGuard already handles redirect) ──
  useEffect(() => {
    if (authUser) {
      setUser(authUser as User)
      setLoading(false)
    }
  }, [authUser])

  // ── Data loading ──
  const loadAffairs = useCallback(async () => {
    try {
      const data = await fetchActiveAffairsSummary()
      setAffairs(data.affairs || [])
    } catch {}
  }, [])

  const loadOrphans = useCallback(async () => {
    try {
      const data = await fetchOrphanArticles(100)
      setOrphans(data.orphans || [])
    } catch {}
  }, [])

  const loadUsers = useCallback(async () => {
    try {
      const data = await fetchUsers()
      setUsers(data.users || [])
    } catch {}
  }, [])

  const loadLog = useCallback(async () => {
    try {
      const data = await fetchAdminActivityLog(50)
      setActivityLog(data.events || [])
    } catch {}
  }, [])

  useEffect(() => {
    if (!user) return
    loadAffairs()
    loadOrphans()
    if (user.role === 'admin') {
      loadUsers()
    }
    loadLog()
  }, [user, loadAffairs, loadOrphans, loadUsers, loadLog])

  // ── Actions ──
  const showMsg = (msg: string) => {
    setActionMsg(msg)
    setTimeout(() => setActionMsg(''), 4000)
  }

  const isEditor = user?.role === 'admin' || user?.role === 'editor'

  const handleMerge = async () => {
    if (selectedAffairs.size < 2) return showMsg('Sélectionnez au moins 2 affaires')
    const ids = Array.from(selectedAffairs)
    // Le premier est celui qu'on garde (le plus grave)
    const sorted = ids
      .map(id => affairs.find(a => a._id === id)!)
      .filter(Boolean)
      .sort((a, b) => (b.gravity_score || 0) - (a.gravity_score || 0))
    const keepId = sorted[0]._id
    const mergeIds = sorted.slice(1).map(a => a._id)

    try {
      const res = await mergeAffairs(keepId, mergeIds, 'Fusion manuelle admin')
      showMsg(`Fusion réussie : ${res.merged} affaire(s) fusionnée(s)`)
      setSelectedAffairs(new Set())
      loadAffairs()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const handleLinkOrphan = async (affairId: string) => {
    if (!selectedOrphan) return showMsg('Sélectionnez un article orphelin')
    try {
      await linkArticleToAffair(affairId, selectedOrphan)
      showMsg('Article lié avec succès')
      setSelectedOrphan(null)
      loadOrphans()
      loadAffairs()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const handleUnlink = async (affairId: string, articleId: string) => {
    try {
      await unlinkArticleFromAffair(affairId, articleId)
      showMsg('Article délié')
      // Refresh detail
      if (expandedAffair === affairId) {
        const detail = await fetchAffairDetail(affairId)
        setAffairDetail(detail)
      }
      loadAffairs()
      loadOrphans()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const handleArchive = async (affairId: string) => {
    try {
      await archiveAffair(affairId)
      showMsg('Affaire archivée')
      setSelectedAffairs(prev => { const n = new Set(prev); n.delete(affairId); return n })
      loadAffairs()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const handleSaveEdit = async () => {
    if (!editingAffair) return
    try {
      const changes: Record<string, string> = {}
      if (editTitle && editTitle !== editingAffair.title) changes.title = editTitle
      if (editTheme && editTheme !== editingAffair.theme) changes.theme = editTheme
      if (editPriority && editPriority !== editingAffair.priority) changes.priority = editPriority
      if (Object.keys(changes).length === 0) return showMsg('Aucune modification')
      await reclassifyAffair(editingAffair._id, changes)
      showMsg('Affaire modifiée')
      setEditingAffair(null)
      loadAffairs()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const handleExpandAffair = async (affairId: string) => {
    if (expandedAffair === affairId) {
      setExpandedAffair(null)
      setAffairDetail(null)
      return
    }
    setExpandedAffair(affairId)
    try {
      const detail = await fetchAffairDetail(affairId)
      setAffairDetail(detail)
    } catch {
      setAffairDetail(null)
    }
  }

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await updateUserRole(userId, newRole)
      showMsg(`Rôle mis à jour : ${newRole}`)
      loadUsers()
    } catch (e: any) {
      showMsg(`Erreur : ${e.message}`)
    }
  }

  const toggleAffairSelect = (id: string) => {
    setSelectedAffairs(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  // ── Auth guard ──
  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="lg:ml-60 flex-1 min-h-screen flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-2 border-indigo-400 border-t-transparent rounded-full" />
        </main>
      </div>
    )
  }

  if (authError || !user) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="lg:ml-60 flex-1 min-h-screen flex items-center justify-center p-4">
          <div className="glass-card-static p-8 max-w-md w-full text-center">
            <div className="w-12 h-12 mx-auto mb-4 rounded-xl flex items-center justify-center" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.15)' }}>
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-white mb-2">Accès restreint</h2>
            <p className="text-sm mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>{authError || 'Connectez-vous pour accéder à cette page'}</p>
            <a href="/auth/login" className="btn-primary inline-block px-5 py-2.5 text-sm">
              Se connecter
            </a>
          </div>
        </main>
      </div>
    )
  }

  const tabs: { key: Tab; label: string; adminOnly?: boolean }[] = [
    { key: 'affairs', label: 'Affaires' },
    { key: 'orphans', label: `Orphelins (${orphans.length})` },
    { key: 'users', label: 'Utilisateurs', adminOnly: true },
    { key: 'log', label: 'Journal' },
  ]

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-4 lg:p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Administration</h1>
          <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
            {user.name || user.email} · <span className="capitalize font-medium" style={{ color: '#818cf8' }}>{user.role}</span>
          </p>
        </div>
        {actionMsg && (
          <div className="px-4 py-2 rounded-xl text-sm animate-fade-in" style={{ background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.2)', color: '#a5b4fc' }}>
            {actionMsg}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.03)' }}>
        {tabs.filter(t => !t.adminOnly || user.role === 'admin').map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === t.key
                ? 'text-white'
                : 'text-white/40 hover:text-white/70'
            }`}
            style={tab === t.key ? { background: 'rgba(99,102,241,0.15)', color: '#a5b4fc' } : {}}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ═══ TAB : AFFAIRES ═══ */}
      {tab === 'affairs' && (
        <div>
          {/* Actions bar */}
          {isEditor && selectedAffairs.size > 0 && (
            <div className="mb-4 flex items-center gap-3 p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
              <span className="text-sm text-indigo-300">{selectedAffairs.size} sélectionnée(s)</span>
              <button
                onClick={handleMerge}
                disabled={selectedAffairs.size < 2}
                className="px-3 py-1.5 bg-amber-600 text-white text-xs rounded-lg hover:bg-amber-500 disabled:opacity-40 transition"
              >
                Fusionner
              </button>
              {selectedOrphan && selectedAffairs.size === 1 && (
                <button
                  onClick={() => handleLinkOrphan(Array.from(selectedAffairs)[0])}
                  className="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-500 transition"
                >
                  Lier l'orphelin sélectionné ici
                </button>
              )}
              <button
                onClick={() => setSelectedAffairs(new Set())}
                className="ml-auto text-xs text-white/40 hover:text-white/60"
              >
                Désélectionner tout
              </button>
            </div>
          )}

          {/* Affair list */}
          <div className="space-y-2">
            {affairs.map(affair => (
              <div key={affair._id}>
                <div
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    selectedAffairs.has(affair._id)
                      ? 'bg-indigo-500/10 border-indigo-500/40'
                      : 'bg-white/[0.025] border-white/[0.05] hover:bg-white/[0.04]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Checkbox */}
                    {isEditor && (
                      <input
                        type="checkbox"
                        checked={selectedAffairs.has(affair._id)}
                        onChange={() => toggleAffairSelect(affair._id)}
                        className="mt-1 w-4 h-4 rounded accent-indigo-500"
                      />
                    )}

                    {/* Content */}
                    <div className="flex-1 min-w-0" onClick={() => handleExpandAffair(affair._id)}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${priorityBadge(affair.priority)}`}>
                          {affair.priority || 'minor'}
                        </span>
                        <span className={`text-xs font-mono ${gravityColor(affair.gravity_score)}`}>
                          {affair.gravity_score?.toFixed(2)}
                        </span>
                        <span className="text-xs text-white/30">{affair.item_count} items</span>
                        <span className="text-xs text-white/30">{affair.theme}</span>
                      </div>
                      <h3 className="text-sm font-medium text-white mt-1 truncate">{affair.title}</h3>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        {(affair.elected || affair.entities || []).slice(0, 3).map((e, i) => (
                          <span key={i} className="text-[10px] px-2 py-0.5 bg-white/5 text-white/50 rounded-full">{e}</span>
                        ))}
                        <span className="text-[10px] text-white/20 ml-auto">{timeAgo(affair.last_activity)}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    {isEditor && (
                      <div className="flex gap-1 shrink-0">
                        <button
                          onClick={() => {
                            setEditingAffair(affair)
                            setEditTitle(affair.title)
                            setEditTheme(affair.theme)
                            setEditPriority(affair.priority || 'minor')
                          }}
                          className="p-1.5 rounded-lg hover:bg-white/10 text-white/30 hover:text-blue-400 transition"
                          title="Modifier"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                        </button>
                        <button
                          onClick={() => handleArchive(affair._id)}
                          className="p-1.5 rounded-lg hover:bg-white/10 text-white/30 hover:text-red-400 transition"
                          title="Archiver"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" /></svg>
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Expanded detail */}
                {expandedAffair === affair._id && affairDetail && (
                  <div className="ml-7 mt-1 mb-2 p-4 bg-white/[0.02] border border-white/[0.05] rounded-xl space-y-3">
                    <h4 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Articles liés ({affairDetail.linked_articles.length})</h4>
                    {affairDetail.linked_articles.map(art => (
                      <div key={art._id} className="flex items-center gap-2 text-xs p-2 bg-white/[0.03] rounded-lg">
                        <span className="flex-1 text-white/70 truncate">{art.title}</span>
                        <span className="text-white/30">{art.source}</span>
                        <span className={`font-mono ${gravityColor(art.gravity_score || 0)}`}>{(art.gravity_score || 0).toFixed(2)}</span>
                        {isEditor && (
                          <button
                            onClick={() => handleUnlink(affair._id, art._id)}
                            className="text-red-400/50 hover:text-red-400 transition"
                            title="Délier"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        )}
                      </div>
                    ))}
                    {affairDetail.linked_radio.length > 0 && (
                      <>
                        <h4 className="text-xs font-semibold text-white/60 uppercase tracking-wide mt-3">Radio ({affairDetail.linked_radio.length})</h4>
                        {affairDetail.linked_radio.map((r, i) => (
                          <div key={i} className="text-xs p-2 bg-white/[0.03] rounded-lg text-white/50">
                            <span className="text-amber-400/70">{r.radio}</span> — {r.topic_title || r.summary || r.text?.slice(0, 100)}
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══ TAB : ORPHELINS ═══ */}
      {tab === 'orphans' && (
        <div>
          <p className="text-sm text-white/40 mb-4">
            Articles enrichis non rattachés à une affaire. Sélectionnez-en un, puis allez dans "Affaires" pour le lier.
          </p>
          <div className="space-y-1">
            {orphans.map(art => (
              <div
                key={art._id}
                onClick={() => setSelectedOrphan(art._id === selectedOrphan ? null : art._id)}
                className={`p-3 rounded-xl border cursor-pointer transition-all ${
                  selectedOrphan === art._id
                    ? 'bg-emerald-500/10 border-emerald-500/30'
                    : 'bg-white/[0.025] border-white/[0.05] hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm text-white/80 truncate">{art.title}</h4>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] text-white/30">{art.source}</span>
                      <span className="text-[10px] text-white/30">{art.theme}</span>
                      <span className={`text-[10px] font-mono ${gravityColor(art.gravity_score)}`}>{art.gravity_score?.toFixed(2)}</span>
                      {art.elected?.slice(0, 2).map((e, i) => (
                        <span key={i} className="text-[10px] px-1.5 py-0.5 bg-white/5 text-white/40 rounded-full">{e}</span>
                      ))}
                      <span className="text-[10px] text-white/20 ml-auto">{timeAgo(art.scraped_at)}</span>
                    </div>
                  </div>
                  {selectedOrphan === art._id && (
                    <span className="text-xs text-emerald-400">Sélectionné</span>
                  )}
                </div>
              </div>
            ))}
            {orphans.length === 0 && (
              <p className="text-center text-white/30 text-sm py-8">Aucun article orphelin</p>
            )}
          </div>
        </div>
      )}

      {/* ═══ TAB : USERS ═══ */}
      {tab === 'users' && user.role === 'admin' && (
        <div>
          <p className="text-sm text-white/40 mb-4">
            Gérez les rôles : <span className="text-red-400">admin</span> (tout), <span className="text-amber-400">editor</span> (pilotage affaires), <span className="text-blue-400">viewer</span> (lecture seule), <span className="text-white/50">user</span> (standard).
          </p>
          <div className="space-y-2">
            {users.map(u => (
              <div key={u._id} className="flex items-center gap-4 p-4 bg-white/[0.03] border border-white/[0.06] rounded-xl">
                <div className="flex-1">
                  <span className="text-sm text-white font-medium">{u.name || u.email}</span>
                  <span className="text-xs text-white/30 ml-2">{u.email}</span>
                </div>
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u._id, e.target.value)}
                  disabled={u._id === user.id}
                  className="bg-white/5 border border-white/10 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-30"
                >
                  <option value="admin">admin</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                  <option value="user">user</option>
                </select>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══ TAB : LOG ═══ */}
      {tab === 'log' && (
        <div>
          <div className="space-y-1">
            {activityLog.map(evt => (
              <div key={evt._id} className="flex items-start gap-3 p-3 bg-white/[0.03] border border-white/[0.06] rounded-xl text-xs">
                <span className={`shrink-0 px-2 py-0.5 rounded-full font-medium ${
                  evt.event.includes('merge') ? 'bg-amber-500/20 text-amber-300' :
                  evt.event.includes('link') ? 'bg-emerald-500/20 text-emerald-300' :
                  evt.event.includes('archive') ? 'bg-red-500/20 text-red-300' :
                  evt.event.includes('reclassify') ? 'bg-blue-500/20 text-blue-300' :
                  'bg-white/10 text-white/50'
                }`}>
                  {evt.event.replace('manual_', '')}
                </span>
                <div className="flex-1 text-white/50">
                  {evt.details?.by && <span className="text-indigo-400">{String(evt.details.by)}</span>}
                  {evt.details?.merged_title && <span> a fusionné "{String(evt.details.merged_title)}"</span>}
                  {evt.details?.article_title && <span> a lié "{String(evt.details.article_title)}"</span>}
                  {evt.details?.changes && <span> a modifié {Object.keys(evt.details.changes as object).join(', ')}</span>}
                </div>
                <span className="text-white/20 shrink-0">{timeAgo(evt.timestamp)}</span>
              </div>
            ))}
            {activityLog.length === 0 && (
              <p className="text-center text-white/30 text-sm py-8">Aucune action manuelle enregistrée</p>
            )}
          </div>
        </div>
      )}

      {/* ═══ MODAL EDIT ═══ */}
      {editingAffair && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setEditingAffair(null)}>
          <div className="bg-[#1a1a2e] border border-white/10 rounded-2xl p-6 max-w-md w-full shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-white mb-4">Modifier l'affaire</h3>

            <label className="block text-xs text-white/50 mb-1">Titre</label>
            <input
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white mb-3 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />

            <label className="block text-xs text-white/50 mb-1">Thème</label>
            <select
              value={editTheme}
              onChange={e => setEditTheme(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white mb-3 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              {['politique', 'economie', 'social', 'securite', 'justice', 'environnement', 'sante', 'education', 'transport', 'culture', 'sport', 'general'].map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>

            <label className="block text-xs text-white/50 mb-1">Priorité</label>
            <div className="flex gap-2 mb-4">
              {['hot', 'watch', 'minor'].map(p => (
                <button
                  key={p}
                  onClick={() => setEditPriority(p)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                    editPriority === p ? priorityBadge(p) : 'border-white/10 text-white/30'
                  }`}
                >
                  {p.toUpperCase()}
                </button>
              ))}
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setEditingAffair(null)} className="px-4 py-2 text-sm text-white/50 hover:text-white transition">
                Annuler
              </button>
              <button onClick={handleSaveEdit} className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 transition">
                Sauvegarder
              </button>
            </div>
          </div>
        </div>
      )}
        </div>
      </main>
    </div>
  )
}
