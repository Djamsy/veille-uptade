'use client'

/**
 * Page de validation d'une publication — accès par lien à jeton (sans connexion), pensée pour
 * le téléphone : carrousel des médias, aperçu « façon post », barre de décision fixée en bas.
 *
 * Le jeton (256 bits) est dans l'URL ; côté serveur seule son empreinte est stockée
 * et le contenu est chiffré au repos. Le lien devient inutilisable dès la décision.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams } from 'next/navigation'
import { fetchPublicationByToken, decidePublication, type PubValidationView } from '../../../lib/api'
import { GuadeloupeMark } from '../../../components/GuadeloupeMark'
import { displayUrl, isImageUrl, isVideoUrl, mediaName, videoUrl } from '../../../lib/media'

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }
const label = 'font-mono text-[10px] uppercase tracking-[0.18em]'
const input: React.CSSProperties = { background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }

function Shell({ children, pill }: { children: React.ReactNode; pill?: string }) {
  return (
    <div className="theme-clair relative min-h-screen flex flex-col overflow-x-hidden">
      <GuadeloupeMark className="pointer-events-none absolute -right-24 -top-12 w-[460px] h-auto hidden md:block" stroke="#1FB6A6" style={{ opacity: 0.04 }} />
      <header className="relative z-10" style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--accent-press)' }}><span className="text-[10px] font-bold" style={{ color: '#fafafa' }}>VM</span></div>
          <div>
            <div className={label} style={{ color: 'var(--text-muted)' }}>Veille Média Guadeloupe</div>
            <div className="text-sm font-semibold tracking-tight">Validation de publication</div>
          </div>
          {pill && <span className="ml-auto text-[10px] px-2 py-1 rounded" style={{ background: 'var(--warn-soft)', color: 'var(--warning)' }}>{pill}</span>}
        </div>
      </header>
      <div className="relative z-10 max-w-2xl mx-auto w-full flex-1 flex flex-col">{children}</div>
      <footer className="relative z-10 px-6 py-3 text-[11px] text-center" style={{ color: 'var(--text-muted)' }}>Page affiliée à Veille Média Guadeloupe · lien personnel, contenu chiffré au repos</footer>
    </div>
  )
}

function Message({ kicker, title, body, tone = 'neutral' }: { kicker: string; title: string; body: string; tone?: 'neutral' | 'bad' | 'good' }) {
  const color = tone === 'bad' ? 'var(--negative)' : tone === 'good' ? 'var(--positive)' : 'var(--text-muted)'
  return (
    <div className="m-4 p-8 text-center elev-card" style={card}>
      <div className={`${label} mb-3`} style={{ color }}>{kicker}</div>
      <h1 className="font-serif text-2xl font-medium italic mb-2 tracking-tight">{title}</h1>
      <p className="text-sm m-0" style={{ color: 'var(--text-secondary)' }}>{body}</p>
    </div>
  )
}

function Slide({ u }: { u: string }) {
  const [broken, setBroken] = useState(false)
  const base = 'flex-none w-[86%] sm:w-[70%] h-[300px] rounded-xl overflow-hidden snap-center'
  const box = { background: 'var(--bg-elevated)', border: '1px solid var(--border)' }
  if (isVideoUrl(u)) return <a href={u} target="_blank" rel="noopener noreferrer nofollow" className={base} style={box}><video src={videoUrl(u)} className="w-full h-full object-cover" controls muted preload="metadata" /></a>
  if (isImageUrl(u) && !broken) {
    // eslint-disable-next-line @next/next/no-img-element
    return <a href={u} target="_blank" rel="noopener noreferrer nofollow" className={base} style={box}><img src={displayUrl(u, 1000)} alt="" className="w-full h-full object-cover" onError={() => setBroken(true)} /></a>
  }
  return (
    <a href={u} target="_blank" rel="noopener noreferrer nofollow" className={`${base} flex flex-col items-center justify-center gap-1 text-xs text-center px-4`} style={{ ...box, color: 'var(--text-muted)' }}>
      <span>{broken ? 'Image non affichable ici' : 'Fichier'}</span><span className="break-all">{mediaName(u)}</span><span className="underline" style={{ color: 'var(--accent-link)' }}>ouvrir</span>
    </a>
  )
}

export default function ValidatePublicationPage() {
  const params = useParams()
  const token = params?.token as string

  const [data, setData] = useState<PubValidationView | null>(null)
  const [errorCode, setErrorCode] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [slide, setSlide] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)

  const [validator, setValidator] = useState('')
  const [comment, setComment] = useState('')
  const [showComment, setShowComment] = useState(false)
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

  const onScroll = () => {
    const el = trackRef.current
    if (!el || !el.firstElementChild) return
    const w = (el.firstElementChild as HTMLElement).offsetWidth + 8
    setSlide(Math.round(el.scrollLeft / w))
  }

  const submit = async (decision: 'approve' | 'reject') => {
    if (!validator.trim()) { setSubmitError('Indiquez votre nom pour signer la décision.'); setConfirm(null); return }
    setSubmitting(true); setSubmitError('')
    try {
      setResult(await decidePublication(token, { decision, validator_name: validator.trim(), comment: comment.trim() || undefined, edited_text: editing && text.trim() !== data?.text ? text.trim() : undefined }))
    } catch (e) {
      const st = (e as { status?: number })?.status
      setSubmitError(st === 409 ? 'Cette publication a déjà été traitée.' : st === 410 ? 'Ce lien a expiré.' : st === 404 ? 'Ce lien n’est plus valide.' : st === 429 ? 'Trop de tentatives, patientez un instant.' : 'Échec de l’envoi, réessayez.')
    } finally { setSubmitting(false); setConfirm(null) }
  }

  if (loading) return <Shell><div className="font-mono text-xs animate-pulse text-center py-24" style={{ color: 'var(--text-muted)' }}>Déchiffrement…</div></Shell>
  if (errorCode || !data) {
    const m = errorCode === 410 ? { kicker: 'Lien expiré', title: 'Ce lien n’est plus actif', body: 'Le délai de validation est dépassé. Demandez un nouveau lien à l’équipe.' }
      : errorCode === 429 ? { kicker: 'Patientez', title: 'Trop de requêtes', body: 'Réessayez dans quelques instants.' }
        : { kicker: 'Accès refusé', title: 'Lien invalide', body: 'Ce lien n’existe pas, a été révoqué ou a déjà servi.' }
    return <Shell><Message tone="bad" {...m} /></Shell>
  }
  if (result) {
    const good = result.status === 'approved'
    return <Shell><Message tone={good ? 'good' : 'neutral'} kicker="Décision enregistrée" title={result.status_label} body={good ? 'Merci. L’équipe publiera la publication.' : 'Refus enregistré. Le demandeur sera informé.'} /></Shell>
  }

  const decided = data.status !== 'pending'
  const media = data.media_urls
  const hl = data.expires_at ? Math.max(0, Math.round((new Date(data.expires_at).getTime() - Date.now()) / 3600000)) : null
  const hashtags = data.hashtags ?? []
  const textWithoutTags = text

  return (
    <Shell pill={!decided && hl != null ? `expire dans ${hl} h` : undefined}>
      <div className="flex flex-col gap-4 pb-44 pt-3">
        {/* Carrousel */}
        {media.length > 0 && (
          <div className="flex flex-col gap-2">
            <div ref={trackRef} onScroll={onScroll} className="flex gap-2 px-4 overflow-x-auto snap-x snap-mandatory" style={{ scrollbarWidth: 'none' }}>
              {media.map((u) => <Slide key={u} u={u} />)}
            </div>
            {media.length > 1 && (
              <div className="flex justify-center items-center gap-1.5" aria-label={`Média ${slide + 1} sur ${media.length}`}>
                {media.map((u, i) => <span key={u} className="rounded-full" style={{ width: 6, height: 6, background: i === slide ? 'var(--accent-press)' : 'var(--border-hover)' }} />)}
                <span className="ml-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>{slide + 1} / {media.length}</span>
              </div>
            )}
          </div>
        )}

        {/* Titre + puces */}
        <div className="flex flex-col gap-2 px-4">
          <span className={label} style={{ color: 'var(--text-muted)' }}>
            {data.requester ? `Demandée par ${data.requester}` : data.kind === 'video' ? 'Vidéo livrée' : 'Publication à valider'}{decided ? ` · ${data.status_label}` : ''}
          </span>
          <h1 className="m-0 font-serif italic font-medium text-2xl leading-tight tracking-tight">{data.title || 'Sans titre'}</h1>
          <div className="flex flex-wrap gap-1.5">
            {data.scheduled_for && <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{data.scheduled_for}</span>}
            {data.location && <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{data.location}</span>}
            {data.networks.length > 0 && <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--info-soft)', border: '1px solid var(--border)', color: 'var(--accent-link)' }}>{data.networks.join(' · ')}</span>}
            {data.provider && <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{data.service ? `${data.service} · ` : ''}{data.provider}</span>}
          </div>
        </div>

        {/* Aperçu façon post */}
        <div className="mx-4 p-3.5 flex flex-col gap-2.5 elev-card" style={card}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0" style={{ background: 'var(--accent-press)', color: '#fafafa' }}><span className="text-[10px] font-bold">CD</span></div>
            <div className="flex flex-col leading-tight">
              <span className="text-sm font-semibold">Département de la Guadeloupe</span>
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Aperçu du post</span>
            </div>
            {!decided && (
              <button type="button" onClick={() => { setEditing((v) => !v); if (editing) setText(data.text) }} className="ml-auto text-[11px] px-2.5 py-1.5 rounded-md" style={{ border: '1px solid var(--border-hover)', color: 'var(--text-secondary)', background: 'var(--bg-surface)' }}>
                {editing ? 'Annuler' : 'Modifier le texte'}
              </button>
            )}
          </div>
          {editing ? (
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} maxLength={5000} aria-label="Texte du post" className="w-full text-sm leading-relaxed p-3 rounded-md outline-none" style={input} />
          ) : (
            <p className="m-0 text-sm leading-relaxed whitespace-pre-wrap">{textWithoutTags || '—'}</p>
          )}
          {hashtags.length > 0 && !editing && !hashtags.every((h) => text.includes(`#${h}`)) && <span className="text-[13px]" style={{ color: 'var(--accent-link)' }}>{hashtags.map((h) => `#${h}`).join(' ')}</span>}
        </div>

        {data.notes && (
          <div className="mx-4 px-3.5 py-3 text-xs" style={{ borderLeft: '3px solid var(--caution)', background: 'var(--caution-soft)', borderRadius: '0 8px 8px 0', color: 'var(--text-secondary)' }}>
            <span className={`${label} block mb-1`} style={{ color: 'var(--text-muted)' }}>Consignes</span>{data.notes}
          </div>
        )}

        {(data.links?.length ?? 0) > 0 && (
          <div className="mx-4 flex flex-col gap-1.5">
            <span className={label} style={{ color: 'var(--text-muted)' }}>Fichiers à consulter</span>
            {data.links!.map((u) => (
              <a key={u} href={u} target="_blank" rel="noopener noreferrer nofollow" className="flex items-center gap-2.5 px-3 py-2.5 text-sm no-underline" style={{ ...card, color: 'var(--text)' }}>
                <span className="flex flex-col leading-tight"><span className="font-semibold">{u.includes('we.tl') || u.includes('wetransfer') ? 'WeTransfer' : u.includes('filemail') ? 'Purevision' : 'Lien'}</span><span className="text-[11px] break-all" style={{ color: 'var(--text-muted)' }}>{u.replace(/^https?:\/\//, '')}</span></span>
                <span className="ml-auto underline text-xs" style={{ color: 'var(--accent-link)' }}>ouvrir</span>
              </a>
            ))}
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Visionnez le fichier avant de décider. Il sera joint par l’équipe au moment de publier.</span>
          </div>
        )}

        {decided && data.decision && (
          <div className="mx-4 p-3.5 elev-card text-sm" style={card}>
            <b>{data.decision.decision === 'approve' ? 'Validée' : 'Refusée'}</b> par {data.decision.by}{data.decision.at && <> le {new Date(data.decision.at).toLocaleString('fr-FR')}</>}{data.decision.comment && <> — « {data.decision.comment} »</>}
          </div>
        )}

        {!decided && <p className="mx-4 m-0 text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>Lien personnel et à usage unique : il sera désactivé dès votre décision. Votre nom et l’heure sont enregistrés.</p>}
      </div>

      {/* Barre de décision fixe */}
      {!decided && (
        <div className="fixed left-0 right-0 bottom-0 z-20" style={{ background: 'var(--bg-surface)', borderTop: '1px solid var(--border)', boxShadow: '0 -8px 24px rgba(0,0,0,0.06)' }}>
          <div className="max-w-2xl mx-auto px-4 pt-3 pb-4 flex flex-col gap-2.5">
            {submitError && <div className="text-xs" style={{ color: 'var(--negative)' }}>{submitError}</div>}
            {confirm ? (
              <div className="flex items-center gap-2 flex-wrap p-3 rounded-md" style={{ background: 'var(--bg-elevated)' }}>
                <span className="text-sm">Confirmer : <b>{confirm === 'approve' ? 'valider' : 'refuser'}</b>{editing && text.trim() !== data.text && ' avec le texte modifié'} ?</span>
                <button type="button" disabled={submitting} onClick={() => submit(confirm)} className="ml-auto text-sm font-semibold px-4 py-2 rounded-md" style={{ background: confirm === 'approve' ? 'var(--positive)' : 'var(--negative)', color: '#fff', opacity: submitting ? 0.6 : 1 }}>{submitting ? 'Envoi…' : 'Oui, confirmer'}</button>
                <button type="button" disabled={submitting} onClick={() => setConfirm(null)} className="text-sm underline" style={{ color: 'var(--text-muted)' }}>Annuler</button>
              </div>
            ) : (
              <>
                <input value={validator} onChange={(e) => setValidator(e.target.value)} placeholder="Votre nom (obligatoire)" maxLength={120} aria-label="Votre nom"
                  className="text-sm p-3 rounded-lg outline-none min-h-[44px]" style={input} />
                {showComment && <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Commentaire pour l’équipe (facultatif)" maxLength={2000} aria-label="Commentaire" className="text-sm p-3 rounded-lg outline-none" style={input} />}
                <div className="grid grid-cols-2 gap-2.5">
                  <button type="button" onClick={() => setConfirm('reject')} className="min-h-[48px] rounded-lg text-[15px] font-semibold" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-hover)', color: 'var(--negative)' }}>✕ Refuser</button>
                  <button type="button" onClick={() => setConfirm('approve')} className="min-h-[48px] rounded-lg text-[15px] font-semibold" style={{ background: 'var(--positive)', border: '1px solid var(--positive)', color: '#fff' }}>✓ Valider</button>
                </div>
                {!showComment && <button type="button" onClick={() => setShowComment(true)} className="text-xs underline self-center" style={{ color: 'var(--text-muted)' }}>Ajouter un commentaire</button>}
              </>
            )}
          </div>
        </div>
      )}
    </Shell>
  )
}
