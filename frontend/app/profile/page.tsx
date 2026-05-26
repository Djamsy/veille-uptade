'use client'

import { useState } from 'react'
import Sidebar from '../../components/Sidebar'
import { useAuth } from '../../components/AuthGuard'
import { changePassword } from '../../lib/api'

function roleLabel(role: string): string {
  switch (role) {
    case 'admin': return 'Administrateur'
    case 'editor': return 'Éditeur'
    case 'viewer': return 'Visualiseur'
    default: return 'Utilisateur'
  }
}

function roleColor(role: string): string {
  switch (role) {
    case 'admin': return 'var(--negative)'
    case 'editor': return 'var(--warning)'
    case 'viewer': return 'var(--accent-link)'
    default: return 'var(--positive)'
  }
}

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
    } catch (e: unknown) {
      showMsg(e instanceof Error ? e.message : 'Erreur lors du changement', 'error')
    } finally {
      setLoading(false)
    }
  }

  const role = user?.role || 'user'
  const rColor = roleColor(role)

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
            Système / Profil
          </div>
          <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
            Mon profil
          </h1>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-2xl mx-auto space-y-5">
          {/* Info user */}
          <div
            className="p-5"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
          >
            <div className="flex items-center gap-4">
              <div
                className="w-14 h-14 rounded-md grid place-items-center font-serif text-xl font-semibold"
                style={{
                  background: 'var(--bg-elevated)',
                  border: `1px solid ${rColor}`,
                  color: rColor,
                }}
              >
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="font-serif text-lg font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
                  {user?.name || 'Utilisateur'}
                </h2>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{user?.email}</p>
                <span
                  className="inline-block font-mono text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-sm mt-2"
                  style={{
                    background: 'var(--bg-elevated)',
                    color: rColor,
                    border: `1px solid ${rColor}40`,
                  }}
                >
                  {roleLabel(role)}
                </span>
              </div>
            </div>
          </div>

          {/* Change password */}
          <div
            className="p-5"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-3" style={{ color: 'var(--text-muted)' }}>
              Sécurité
            </div>
            <h3 className="font-serif text-base font-semibold tracking-tight mb-4" style={{ color: 'var(--text)' }}>
              Changer le mot de passe
            </h3>

            {msg && (
              <div
                className="mb-4 px-4 py-2.5 text-xs"
                style={{
                  background: msgType === 'success' ? 'var(--ok-soft)' : 'var(--crit-soft)',
                  color: msgType === 'success' ? '#3d6f44' : '#b02939',
                  border: `1px solid ${msgType === 'success' ? '#cce5d0' : '#f5d4d9'}`,
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {msg}
              </div>
            )}

            <div className="space-y-3">
              {[
                { label: 'Mot de passe actuel', value: currentPassword, setter: setCurrentPassword, placeholder: 'Entrez votre mot de passe actuel' },
                { label: 'Nouveau mot de passe', value: newPassword, setter: setNewPassword, placeholder: '6 caractères minimum' },
                { label: 'Confirmer', value: confirmPassword, setter: setConfirmPassword, placeholder: 'Confirmez le mot de passe' },
              ].map(field => (
                <div key={field.label}>
                  <label
                    className="block font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {field.label}
                  </label>
                  <input
                    type="password"
                    value={field.value}
                    onChange={e => field.setter(e.target.value)}
                    placeholder={field.placeholder}
                    className="w-full px-3 py-2 text-sm focus:outline-none"
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--text)',
                    }}
                  />
                </div>
              ))}
              <button
                onClick={handleChangePassword}
                disabled={loading || !currentPassword || !newPassword || !confirmPassword}
                className="w-full mt-2 px-4 py-2.5 text-sm font-semibold rounded-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                style={{ background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }}
              >
                {loading && <span className="animate-spin w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full" />}
                Mettre à jour le mot de passe
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
