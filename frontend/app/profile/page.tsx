'use client'

import { useState } from 'react'
import Sidebar from '../../components/Sidebar'
import { useAuth } from '../../components/AuthGuard'
import { changePassword } from '../../lib/api'

export default function ProfilePage() {
  const { user } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'success' | 'error'>('success')
  const [loading, setLoading] = useState(false)

  const showMsg = (text: string, type: 'success' | 'error') => {
    setMsg(text)
    setMsgType(type)
    setTimeout(() => setMsg(''), 5000)
  }

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword) return showMsg('Tous les champs sont requis', 'error')
    if (newPassword.length < 6) return showMsg('Le nouveau mot de passe doit faire au moins 6 caractères', 'error')
    if (newPassword !== confirmPassword) return showMsg('Les mots de passe ne correspondent pas', 'error')

    setLoading(true)
    try {
      await changePassword(currentPassword, newPassword)
      showMsg('Mot de passe mis à jour avec succès', 'success')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e: any) {
      showMsg(e.message || 'Erreur lors du changement', 'error')
    } finally {
      setLoading(false)
    }
  }

  const roleLabel = (role: string) => {
    switch (role) {
      case 'admin': return 'Administrateur'
      case 'editor': return 'Éditeur'
      case 'viewer': return 'Visualiseur'
      default: return 'Utilisateur'
    }
  }

  const roleColor = (role: string) => {
    switch (role) {
      case 'admin': return '#dc2626'
      case 'editor': return '#eab308'
      case 'viewer': return '#2563eb'
      default: return '#16a34a'
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-5 lg:p-8 min-h-screen">
        <div className="max-w-2xl mx-auto animate-fade-in">
          <h1 className="text-xl font-bold text-white tracking-tight mb-6">Mon profil</h1>

          {/* Info utilisateur */}
          <div className="p-6 bg-white/[0.03] border border-white/[0.06] rounded-2xl mb-6">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-14 h-14 rounded-xl flex items-center justify-center text-xl font-bold text-white"
                style={{
                  background: `linear-gradient(135deg, ${roleColor(user?.role || 'user')}40, ${roleColor(user?.role || 'user')}20)`,
                  border: `1px solid ${roleColor(user?.role || 'user')}50`,
                }}>
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">{user?.name || 'Utilisateur'}</h2>
                <p className="text-sm text-white/40">{user?.email}</p>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider mt-1 inline-block"
                  style={{ background: `${roleColor(user?.role || 'user')}20`, color: roleColor(user?.role || 'user'), border: `1px solid ${roleColor(user?.role || 'user')}30` }}>
                  {roleLabel(user?.role || 'user')}
                </span>
              </div>
            </div>
          </div>

          {/* Changer le mot de passe */}
          <div className="p-6 bg-white/[0.03] border border-white/[0.06] rounded-2xl">
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>
              Changer le mot de passe
            </h3>

            {msg && (
              <div className="mb-4 px-4 py-2.5 rounded-xl text-sm" style={{
                background: msgType === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                border: `1px solid ${msgType === 'success' ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                color: msgType === 'success' ? '#34d399' : '#f87171',
              }}>
                {msg}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-white/40 uppercase tracking-wider mb-1">Mot de passe actuel</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Entrez votre mot de passe actuel"
                />
              </div>
              <div>
                <label className="block text-[10px] text-white/40 uppercase tracking-wider mb-1">Nouveau mot de passe</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="6 caractères minimum"
                />
              </div>
              <div>
                <label className="block text-[10px] text-white/40 uppercase tracking-wider mb-1">Confirmer le nouveau mot de passe</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Confirmez le mot de passe"
                />
              </div>
              <button
                onClick={handleChangePassword}
                disabled={loading || !currentPassword || !newPassword || !confirmPassword}
                className="w-full mt-2 px-5 py-2.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-500 disabled:opacity-40 transition flex items-center justify-center gap-2"
              >
                {loading && <span className="animate-spin w-4 h-4 border-2 border-white/50 border-t-white rounded-full" />}
                Mettre à jour le mot de passe
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
