'use client'

/**
 * Page de validation d'une publication — accès par lien à jeton (sans connexion).
 *
 * Le jeton (256 bits) est dans l'URL ; côté serveur seule son empreinte est stockée
 * et le contenu est chiffré au repos. Le lien devient inutilisable dès la décision.
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import {
  fetchPublicationByToken,
  decidePublication,
  type PubValidationView,
} from '../../../lib/api'
import { GuadeloupeMark } from '../../../components/GuadeloupeMark'

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-lg)',
}

const label = 'font-mono text-[10px] uppercase tracking-[0.18em]'

const isVideo = (u: string) => /\.(mp4|mov|m4v|webm)(\?|$)/i.test(u)
const isImage = (u: string) => /\.(jpe?g|png|gif|webp|avif)(\?|$)/i.test(u)

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-hidden" style={{ background: 'var(--bg-base)', color: 'var(--text)' }}>
      <GuadeloupeMark
        className="pointer-events-none absolute -right-24 -top-12 w-[460px] h-auto hidden md:block"
        stroke="#1FB6A6"
        style={{ opacity: 0.04 }}
      />
      <header className="relative z-10" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'var(--brand-gradient)', boxShadow: 'var(--shadow-card)' }}
          >
            <span className="text-sm font-bold" style={{ color: 'var(--on-accent)' }}>VM</span>
          </div>
          <div>
            <div className={label} style={{ color: 'var(--text-muted)' }}>Veille Média Guadeloupe</div>
            <div className="text-sm font-semibold tracking-tight">Validation de publication</div>
          </div>
          <div className="ml-auto flex items-center gap-2 font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            <span aria-hidden>🔐</span> Lien personnel · contenu chiffré
          </div>
        </div>
      </header>
      <div className="relative z-10 max-w-3xl mx-auto px-6 py-8 space-y-5">{children}</div>
    </div>
  )
}

function Message({ kicker, title, body, tone = 'neutral' }: { kicker: string; title: string; body: string; tone?: 'neutral' | 'bad' | 'good' }) {
  const color = tone === 'bad' ? 'var(--negative)' : tone === 'good' ? 'var(--positive)' : 'var(--text-muted)'
  return (
    <div className="p-8 max-w-md mx-auto text-center elev-card" style={card}>
      <div className={`${label} mb-3`} style={{ color }}>{kicker}</div>
      <h1 className="font-serif text-2xl font-medium italic mb-2 tracking-tight">{title}</h1>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{body}</p>
    </div>
  )
}

export default function ValidatePublicationPage() {
  const params = useParams()
  const token = params?.token as string

  const [data, setData] = useState<PubValidationView | null>(null)
  const [errorCode, setErrorCode] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  const [validator, setValidator] = useState('')
  const [comment, setComment] = useState('')
  const [text, setText] = useState('')
  const [editing, setEditing] = useState(false)
  const [confirm, setConfirm] = useState<'approve' | 'reject' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [result, setResult] = useState<{ status: string; status_label: string } | null>(null)

  const load = useCallback(() => {
    if (!token) return
    setLoading(true)
    fetchPublicationByToken(token)
      .then((d) => { setData(d); setText(d.text) })
      .catch((e: { status?: number }) => setErrorCode(e?.status ?? 500))
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => { load() }, [load])

  const submit = async (decision: 'approve' | 'reject') => {
    if (!validator.trim()) { setSubmitError('Indiquez votre nom pour signer la décision.'); return }
    setSubmitting(true)
    setSubmitError('')
    try {
      const r = await decidePublication(token, {
        decision,
        validator_name: validator.trim(),
        comment: comment.trim() || undefined,
        edited_text: editing && text.trim() !== data?.text ? text.trim() : undefined,
      })
      setResult(r)
    } catch (e) {
      const st = (e as { status?: number })?.status
      setSubmitError(
        st === 409 ? 'Cette publication a déjà été traitée.'
          : st === 410 ? 'Ce lien a expiré.'
          : st === 404 ? 'Ce lien n’est plus valide.'
          : st === 429 ? 'Trop de tentatives, patientez un instant.'
          : 'Échec de l’envoi, réessayez.'
      )
    } finally {
      setSubmitting(false)
      setConfirm(null)
    }
  }

  if (loading) {
    return (
      <Shell>
        <div className="font-mono text-xs animate-pulse text-center py-20" style={{ color: 'var(--text-muted)' }}>Déchiffrement…</div>
      </Shell>
    )
  }

  if (errorCode || !data) {
    const m = errorCode === 410
      ? { kicker: 'Lien expiré', title: 'Ce lien n’est plus actif', body: 'Le délai de validation est dépassé. Demandez un nouveau lien à l’administrateur.' }
      : errorCode === 429
        ? { kicker: 'Patientez', title: 'Trop de requêtes', body: 'Réessayez dans quelques instants.' }
        : { kicker: 'Accès refusé', title: 'Lien invalide', body: 'Ce lien n’existe pas, a été révoqué ou a déjà servi.' }
    return <Shell><Message tone="bad" {...m} /></Shell>
  }

  if (result) {
    const good = result.status === 'approved'
    const body = good
      ? 'Validée. L’équipe publiera la publication manuellement.'
      : 'Refus enregistré. Le demandeur sera informé.'
    return <Shell><Message tone={good ? 'good' : 'neutral'} kicker="Décision enregistrée" title={result.status_label} body={body} /></Shell>
  }

  const decided = data.status !== 'pending'
  const expires = data.expires_at ? new Date(data.expires_at) : null

  return (
    <Shell>
      {/* En-tête de la demande */}
      <div className="p-6 elev-card" style={card}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <div className={`${label} mb-2`} style={{ color: 'var(--text-muted)' }}>
              Publication à valider {data.requester && <>· demandée par <span style={{ color: 'var(--text)' }}>{data.requester}</span></>}
            </div>
            <h1 className="font-serif text-3xl font-medium italic tracking-tight leading-tight">
              {data.title || 'Sans titre'}
            </h1>
          </div>
          <span
            className="text-[10px] font-medium px-2 py-1 rounded-sm self-start"
            style={{
              background: decided ? 'var(--bg-elevated)' : 'var(--warn-soft)',
              color: decided ? 'var(--text-secondary)' : 'var(--warning)',
              border: '1px solid var(--border)',
            }}
          >
            {data.status_label}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-4">
          {data.networks.map((n) => (
            <span key={n} className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>{n}</span>
          ))}
          {data.scheduled_for && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>📅 {data.scheduled_for}</span>
          )}
          {data.location && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>📍 {data.location}</span>
          )}
          {data.kind === 'video' && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--accent-link)', border: '1px solid var(--border)' }}>🎬 Vidéo livrée</span>
          )}
          {data.service && data.kind !== 'video' && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>🎥 {data.service}</span>
          )}
          {data.provider && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>Prestataire : {data.provider}</span>
          )}
          {data.campaign_name && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>Campagne : {data.campaign_name}</span>
          )}
        </div>
      </div>

      {/* Texte */}
      <div className="p-6 elev-card" style={card}>
        <div className="flex items-center justify-between mb-3">
          <div className={label} style={{ color: 'var(--text-muted)' }}>Texte du post</div>
          {!decided && (
            <button type="button" onClick={() => { setEditing((v) => !v); if (editing) setText(data.text) }}
              className="text-xs underline" style={{ color: 'var(--accent-link)' }}>
              {editing ? 'Annuler la modification' : 'Modifier le texte'}
            </button>
          )}
        </div>
        {editing ? (
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} maxLength={5000}
            className="w-full text-sm leading-relaxed p-3 rounded-md outline-none"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }} />
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>{data.text || '—'}</p>
        )}
        {data.hashtags.length > 0 && !editing && (
          <div className="mt-3 text-xs font-mono" style={{ color: 'var(--accent-link)' }}>
            {data.hashtags.map((h) => `#${h}`).join(' ')}
          </div>
        )}
        {data.notes && (
          <div className="mt-4 pt-4 text-xs" style={{ borderTop: '1px dashed var(--border)', color: 'var(--text-muted)' }}>
            <span className={label}>Consignes · </span>{data.notes}
          </div>
        )}
      </div>

      {/* Liens (WeTransfer, Purevision…) */}
      {(data.links?.length ?? 0) > 0 && (
        <div className="p-6 elev-card" style={card}>
          <div className={`${label} mb-3`} style={{ color: 'var(--text-muted)' }}>Fichiers à consulter ({data.links!.length})</div>
          <ul className="space-y-1.5">
            {data.links!.map((u) => (
              <li key={u}>
                <a href={u} target="_blank" rel="noopener noreferrer nofollow" className="text-sm underline break-all" style={{ color: 'var(--accent-link)' }}>
                  {u.includes('we.tl') || u.includes('wetransfer') ? '📦 WeTransfer · ' : u.includes('filemail') ? '🎬 Purevision · ' : '🔗 '}{u.replace(/^https?:\/\//, '')}
                </a>
              </li>
            ))}
          </ul>
          <p className="text-[11px] mt-3" style={{ color: 'var(--text-muted)' }}>Ouvrez le fichier pour le visionner avant de décider. Il sera joint par l’équipe au moment de publier.</p>
        </div>
      )}

      {/* Médias */}
      {data.media_urls.length > 0 && (
        <div className="p-6 elev-card" style={card}>
          <div className={`${label} mb-3`} style={{ color: 'var(--text-muted)' }}>Médias ({data.media_urls.length})</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {data.media_urls.map((u) => (
              <a key={u} href={u} target="_blank" rel="noopener noreferrer nofollow"
                className="block rounded-md overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--bg-elevated)' }}>
                {isImage(u) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={u} alt="" className="w-full h-32 object-cover" loading="lazy" />
                ) : isVideo(u) ? (
                  <video src={u} className="w-full h-32 object-cover" muted preload="metadata" />
                ) : (
                  <div className="h-32 flex items-center justify-center text-xs px-3 text-center break-all" style={{ color: 'var(--text-muted)' }}>
                    🔗 {u.replace(/^https?:\/\//, '').slice(0, 60)}
                  </div>
                )}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Décision déjà prise */}
      {decided && data.decision && (
        <div className="p-6 elev-card" style={card}>
          <div className={`${label} mb-2`} style={{ color: 'var(--text-muted)' }}>Décision</div>
          <p className="text-sm">
            <b>{data.decision.decision === 'approve' ? 'Validée' : 'Refusée'}</b> par {data.decision.by}
            {data.decision.at && <> le {new Date(data.decision.at).toLocaleString('fr-FR')}</>}
            {data.decision.comment && <> — « {data.decision.comment} »</>}
          </p>
        </div>
      )}

      {/* Formulaire de décision */}
      {!decided && (
        <div className="p-6 elev-card" style={card}>
          <div className={`${label} mb-4`} style={{ color: 'var(--text-muted)' }}>Votre décision</div>
          <div className="grid sm:grid-cols-2 gap-3 mb-3">
            <input value={validator} onChange={(e) => setValidator(e.target.value)} placeholder="Votre nom (obligatoire)" maxLength={120}
              className="text-sm p-3 rounded-md outline-none"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }} />
            <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Commentaire (facultatif)" maxLength={2000}
              className="text-sm p-3 rounded-md outline-none"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }} />
          </div>
          {submitError && <div className="text-xs mb-3" style={{ color: 'var(--negative)' }}>{submitError}</div>}

          {confirm ? (
            <div className="flex items-center gap-3 flex-wrap p-3 rounded-md" style={{ background: 'var(--bg-elevated)' }}>
              <span className="text-sm">
                Confirmer : <b>{confirm === 'approve' ? 'valider' : 'refuser'}</b>
                {editing && text.trim() !== data.text && ' (avec le texte modifié)'} ?
              </span>
              <button type="button" disabled={submitting} onClick={() => submit(confirm)}
                className="text-sm font-medium px-4 py-2 rounded-md"
                style={{ background: confirm === 'approve' ? 'var(--positive)' : 'var(--negative)', color: '#fff', opacity: submitting ? 0.6 : 1 }}>
                {submitting ? 'Envoi…' : 'Oui, confirmer'}
              </button>
              <button type="button" disabled={submitting} onClick={() => setConfirm(null)} className="text-sm underline" style={{ color: 'var(--text-muted)' }}>Annuler</button>
            </div>
          ) : (
            <div className="flex gap-3 flex-wrap">
              <button type="button" onClick={() => setConfirm('approve')}
                className="text-sm font-medium px-5 py-2.5 rounded-md" style={{ background: 'var(--positive)', color: '#fff' }}>
                ✓ Valider
              </button>
              <button type="button" onClick={() => setConfirm('reject')}
                className="text-sm font-medium px-5 py-2.5 rounded-md" style={{ background: 'var(--bg-elevated)', color: 'var(--negative)', border: '1px solid var(--border-hover)' }}>
                ✕ Refuser
              </button>
            </div>
          )}

          <p className="text-[11px] mt-4" style={{ color: 'var(--text-muted)' }}>
            Ce lien est personnel et à usage unique : il sera désactivé dès votre décision
            {expires && <> et expire le {expires.toLocaleString('fr-FR')}</>}. Votre nom et l’horodatage sont journalisés.
          </p>
        </div>
      )}
    </Shell>
  )
}
