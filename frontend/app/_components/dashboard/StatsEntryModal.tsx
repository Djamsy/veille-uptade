'use client'

import { useState } from 'react'
import { setManualFollowers, setManualWebTraffic } from '../../../lib/api'

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram', color: '#e4405f' },
  { id: 'facebook', label: 'Facebook', color: '#1877f2' },
  { id: 'tiktok', label: 'TikTok', color: '#00f2ea' },
]

const WEB_FIELDS: { key: string; label: string; placeholder: string }[] = [
  { key: 'sessions', label: 'Sessions', placeholder: '22725' },
  { key: 'pageviews', label: 'Pages vues', placeholder: '31992' },
  { key: 'users', label: 'Utilisateurs', placeholder: '17647' },
  { key: 'new_users', label: 'Nouveaux utilisateurs', placeholder: '15804' },
  { key: 'avg_session_duration', label: 'Durée moy. session (s)', placeholder: '26' },
  { key: 'bounce_rate', label: 'Taux de rebond (%)', placeholder: '55.9' },
]

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function StatsEntryModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [tab, setTab] = useState<'web' | 'followers'>('web')
  const [date, setDate] = useState(today())
  const [web, setWeb] = useState<Record<string, string>>({})
  const [followers, setFollowers] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const saveWeb = async () => {
    setSaving(true); setMsg(null)
    try {
      const metrics: Record<string, number> = {}
      for (const f of WEB_FIELDS) {
        const v = web[f.key]
        if (v !== undefined && v !== '') metrics[f.key] = parseFloat(v)
      }
      if (Object.keys(metrics).length === 0) { setMsg('Renseigne au moins une valeur.'); setSaving(false); return }
      await setManualWebTraffic(metrics, date)
      setMsg('Trafic web enregistré ✓')
      onSaved()
    } catch {
      setMsg('Erreur — réservé aux administrateurs ?')
    } finally { setSaving(false) }
  }

  const saveFollowers = async () => {
    setSaving(true); setMsg(null)
    try {
      const entries = PLATFORMS.filter(p => followers[p.id] && followers[p.id] !== '')
      if (entries.length === 0) { setMsg('Renseigne au moins une plateforme.'); setSaving(false); return }
      await Promise.all(entries.map(p => setManualFollowers(p.id, parseInt(followers[p.id], 10), date)))
      setMsg('Abonnés enregistrés ✓')
      onSaved()
    } catch {
      setMsg('Erreur — réservé aux administrateurs ?')
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl p-5" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>Saisir des statistiques</h3>
          <button onClick={onClose} className="text-sm" style={{ color: 'var(--text-muted)' }}>✕</button>
        </div>

        {/* Onglets */}
        <div className="flex gap-1 mb-4 p-1 rounded-lg" style={{ background: 'var(--bg-base)' }}>
          {([['web', 'Trafic web'], ['followers', 'Abonnés']] as const).map(([id, label]) => (
            <button key={id} onClick={() => { setTab(id); setMsg(null) }}
              className="flex-1 py-1.5 text-xs font-medium rounded-md transition-colors"
              style={tab === id
                ? { background: 'var(--accent-press)', color: 'var(--on-accent)' }
                : { color: 'var(--text-muted)' }}>
              {label}
            </button>
          ))}
        </div>

        {/* Date commune */}
        <label className="block mb-4">
          <span className="block text-[11px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Date</span>
          <input type="date" value={date} max={today()} onChange={e => setDate(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg"
            style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text)' }} />
        </label>

        {tab === 'web' ? (
          <div className="grid grid-cols-2 gap-3">
            {WEB_FIELDS.map(f => (
              <label key={f.key} className="block">
                <span className="block text-[11px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{f.label}</span>
                <input type="number" step="any" inputMode="decimal" placeholder={f.placeholder}
                  value={web[f.key] ?? ''} onChange={e => setWeb({ ...web, [f.key]: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg tabular-nums"
                  style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text)' }} />
              </label>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {PLATFORMS.map(p => (
              <label key={p.id} className="flex items-center gap-3">
                <span className="w-20 text-xs font-semibold" style={{ color: p.color }}>{p.label}</span>
                <input type="number" inputMode="numeric" placeholder="abonnés"
                  value={followers[p.id] ?? ''} onChange={e => setFollowers({ ...followers, [p.id]: e.target.value })}
                  className="flex-1 px-3 py-2 text-sm rounded-lg tabular-nums"
                  style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text)' }} />
              </label>
            ))}
          </div>
        )}

        {msg && <p className="mt-3 text-[12px]" style={{ color: 'var(--text-muted)' }}>{msg}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-sm"
            style={{ background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
            Annuler
          </button>
          <button onClick={tab === 'web' ? saveWeb : saveFollowers} disabled={saving}
            className="px-4 py-1.5 text-xs font-semibold rounded-sm disabled:opacity-50"
            style={{ background: 'var(--accent-press)', color: 'var(--on-accent)' }}>
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default StatsEntryModal
