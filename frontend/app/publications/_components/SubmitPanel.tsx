'use client'

import { useEffect, useMemo, useState } from 'react'
import type { LibraryMedia, PendingPublication } from '../../../lib/api'
import { displayUrl, isVideoUrl, mediaName } from '../../../lib/media'
import { Icon, btnPrimary, btnSecondary, card, input, label } from './common'

export interface SubmitValues {
  title: string; text: string; networks: string[]; scheduled_for: string; location: string; requester: string;
  requester_email: string; notes: string; ttl_hours: number; notify: boolean;
  files: File[]; libraryIds: string[]; removeMedia: string[]
}

const emptyValues = (): SubmitValues => ({ title: '', text: '', networks: [], scheduled_for: '', location: '', requester: '', requester_email: '', notes: '', ttl_hours: 72, notify: true, files: [], libraryIds: [], removeMedia: [] })

function LibraryThumb({ m, size = 'h-20' }: { m: LibraryMedia; size?: string }) {
  const [broken, setBroken] = useState(false)
  if (m.kind === 'video') return <video src={displayUrl(m.url)} className={`w-full ${size} object-cover`} muted preload="metadata" />
  if (broken) return <div className={`w-full ${size} flex items-center justify-center text-[10px] px-1 text-center`} style={{ color: 'var(--text-muted)' }}>{m.name}</div>
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={displayUrl(m.url, 400)} alt="" title={m.name} className={`w-full ${size} object-cover`} loading="lazy" onError={() => setBroken(true)} />
}

/** Panneau latéral : nouvelle publication ou modification d'une publication en attente. */
export function SubmitPanel({ mode, pub, library, tags, onClose, onSubmit, busy, progress, onDraft }: {
  mode: 'create' | 'edit'; pub?: PendingPublication | null; library: LibraryMedia[]; tags: Record<string, number>;
  onClose: () => void; onSubmit: (v: SubmitValues, resend: boolean) => void; busy: boolean; progress: string; onDraft?: (v: SubmitValues) => void
}) {
  const [v, setV] = useState<SubmitValues>(emptyValues)
  const [showOptions, setShowOptions] = useState(false)
  const [showLibrary, setShowLibrary] = useState(false)
  const [libTag, setLibTag] = useState('')
  const [libQ, setLibQ] = useState('')
  const set = (patch: Partial<SubmitValues>) => setV((cur) => ({ ...cur, ...patch }))

  useEffect(() => {
    if (mode === 'edit' && pub) {
      const p = pub.payload
      setV({ ...emptyValues(), title: p.title ?? '', text: p.text ?? '', networks: p.networks ?? [], scheduled_for: p.scheduled_for ?? '', location: p.location ?? '', requester: p.requester ?? '', requester_email: p.requester_email ?? '', notes: p.notes ?? '' })
      setShowOptions(Boolean(p.networks?.length || p.notes))
    } else {
      setV(emptyValues()); setShowOptions(false)
    }
    setShowLibrary(false)
  }, [mode, pub])

  const previews = useMemo(() => v.files.map((f) => ({ f, url: URL.createObjectURL(f), video: f.type.startsWith('video') })), [v.files])
  useEffect(() => () => { previews.forEach((p) => URL.revokeObjectURL(p.url)) }, [previews])

  const existing = (pub?.payload?.media_urls ?? []).filter((u) => !v.removeMedia.includes(u))
  const picks = v.libraryIds.map((id) => library.find((m) => m.id === id)).filter(Boolean) as LibraryMedia[]
  const total = existing.length + picks.length + v.files.length
  const canSubmit = (v.text.trim().length > 0 || total > 0) && !busy
  const toggleLib = (m: LibraryMedia) => set({ libraryIds: v.libraryIds.includes(m.id) ? v.libraryIds.filter((x) => x !== m.id) : [...v.libraryIds, m.id].slice(0, 10) })

  const libFiltered = library.filter((m) => (!libTag || m.tags.includes(libTag)) && (!libQ || (m.name + ' ' + m.tags.join(' ')).toLowerCase().includes(libQ.toLowerCase())))
  const topTags = Object.keys(tags).slice(0, 8)
  const chars = v.text.length
  const hashtags = (v.text.match(/#\w+/g) ?? []).length

  return (
    <div className="fixed inset-0 z-40" style={{ background: 'rgba(24,24,27,0.35)' }} onClick={onClose}>
      <aside className="absolute top-0 right-0 bottom-0 w-full max-w-[760px] flex flex-col theme-clair" style={{ background: 'var(--bg-surface)', borderLeft: '1px solid var(--border)', boxShadow: '-12px 0 32px rgba(0,0,0,0.12)' }}
        onClick={(e) => e.stopPropagation()} aria-label={mode === 'create' ? 'Nouvelle publication' : 'Modifier la publication'}>
        <div className="flex items-center gap-3 px-6 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className={label} style={{ color: 'var(--text-muted)' }}>
              {mode === 'create' ? 'Soumettre à validation' : pub?.source === 'sheet' ? `Détectée dans ${pub.sheet_tab ?? 'le planning'} · ligne ${pub.sheet_row}` : 'Saisie manuelle'}
            </div>
            <h2 className="m-0 font-serif italic font-medium text-2xl tracking-tight">{mode === 'create' ? 'Nouvelle publication' : 'Modifier avant validation'}</h2>
          </div>
          <button type="button" aria-label="Fermer" onClick={onClose} className="ml-auto w-9 h-9 rounded-md inline-flex items-center justify-center" style={btnSecondary}><Icon name="x" /></button>
        </div>

        <div className="flex-1 overflow-auto px-6 py-5 flex flex-col gap-5">
          {mode === 'edit' && (pub?.status === 'approved' || pub?.status === 'publish_failed') && (
            <div className="text-xs px-3.5 py-3 rounded-md" style={{ background: 'var(--warn-soft)', color: 'var(--warning)', border: '1px solid var(--border)' }}>
              Validée par {pub.decision?.by ?? '—'}. Ajouter ou retirer des médias ne change rien à la validation.
              Modifier le <b>texte</b> ou le <b>titre</b> renverra la publication en validation : un nouveau lien sera envoyé automatiquement.
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="pub-text" className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>Texte du post</label>
            <textarea id="pub-text" rows={8} maxLength={5000} value={v.text} onChange={(e) => set({ text: e.target.value })}
              placeholder="Le texte tel qu'il sera publié. La première ligne sert de titre si le champ Titre est vide. Les #hashtags sont détectés."
              className="text-sm p-3 rounded-md outline-none leading-relaxed resize-y"
              style={{ ...input, display: 'block', width: '100%', minHeight: 180, maxHeight: '50vh', boxSizing: 'border-box' }} />
            <div className="flex gap-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              <span>{chars} caractères</span><span>{hashtags} hashtag{hashtags > 1 ? 's' : ''}</span>
              {pub?.payload?.original_text && <span className="ml-auto">Texte d’origine conservé dans l’historique</span>}
            </div>
            <input value={v.title} onChange={(e) => set({ title: e.target.value })} placeholder="Titre (facultatif)" maxLength={300}
              className="text-sm p-2.5 rounded-md outline-none" style={input} />
          </div>

          {/* Médias */}
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>Médias</span>
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{total} sélectionné{total > 1 ? 's' : ''} · 10 max · l’ordre est celui de la publication</span>
            </div>
            <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
              {existing.map((u, i) => (
                <div key={u} className="relative rounded-md overflow-hidden" style={{ border: '1px solid var(--border)', aspectRatio: '1 / 1' }}>
                  {isVideoUrl(u)
                    ? <video src={displayUrl(u)} className="w-full h-full object-cover" muted preload="metadata" />
                    // eslint-disable-next-line @next/next/no-img-element
                    : <img src={displayUrl(u, 400)} alt="" title={mediaName(u)} className="w-full h-full object-cover" loading="lazy" />}
                  <span className="absolute left-1 bottom-1 text-[10px] font-bold px-1.5 rounded" style={{ background: 'var(--accent-press)', color: '#fafafa' }}>{i + 1}</span>
                  <button type="button" aria-label="Retirer" onClick={() => set({ removeMedia: [...v.removeMedia, u] })}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full text-[10px] inline-flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.65)', color: '#fff' }}><Icon name="x" size={10} stroke={3} /></button>
                </div>
              ))}
              {picks.map((m, i) => (
                <div key={m.id} className="relative rounded-md overflow-hidden" style={{ border: '1px solid var(--accent-link)', aspectRatio: '1 / 1', background: 'var(--bg-elevated)' }}>
                  <LibraryThumb m={m} size="h-full" />
                  <span className="absolute left-1 bottom-1 text-[10px] font-bold px-1.5 rounded" style={{ background: 'var(--accent-press)', color: '#fafafa' }}>{existing.length + i + 1}</span>
                  <span className="absolute left-1 top-1 text-[9px] px-1 rounded" style={{ background: 'rgba(255,255,255,0.85)', color: 'var(--accent-link)' }}>médiathèque</span>
                  <button type="button" aria-label="Retirer" onClick={() => toggleLib(m)}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full inline-flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.65)', color: '#fff' }}><Icon name="x" size={10} stroke={3} /></button>
                </div>
              ))}
              {previews.map((p, i) => (
                <div key={p.url} className="relative rounded-md overflow-hidden" style={{ border: '1px dashed var(--border-strong)', aspectRatio: '1 / 1' }}>
                  {p.video ? <video src={p.url} className="w-full h-full object-cover" muted /> : // eslint-disable-next-line @next/next/no-img-element
                    <img src={p.url} alt="" className="w-full h-full object-cover" />}
                  <span className="absolute left-1 bottom-1 text-[10px] font-bold px-1.5 rounded" style={{ background: 'var(--accent-press)', color: '#fafafa' }}>{existing.length + picks.length + i + 1}</span>
                  <button type="button" aria-label="Retirer" onClick={() => set({ files: v.files.filter((_, j) => j !== i) })}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full inline-flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.65)', color: '#fff' }}><Icon name="x" size={10} stroke={3} /></button>
                </div>
              ))}
              <label className="flex flex-col items-center justify-center gap-1 rounded-md cursor-pointer text-[11px] text-center" style={{ border: '1px dashed var(--border-strong)', background: 'var(--bg-elevated)', aspectRatio: '1 / 1', color: 'var(--text-secondary)' }}>
                <input type="file" accept="image/*,video/*" multiple className="hidden" onChange={(e) => { const add = Array.from(e.target.files ?? []); set({ files: [...v.files, ...add].slice(0, 10) }); e.target.value = '' }} />
                <Icon name="upload" size={18} />Depuis l’ordinateur
              </label>
              <button type="button" onClick={() => setShowLibrary((s) => !s)} aria-expanded={showLibrary}
                className="flex flex-col items-center justify-center gap-1 rounded-md text-[11px]" style={{ ...(showLibrary ? { border: '1px solid var(--accent-press)', background: 'var(--bg-surface)' } : btnSecondary), aspectRatio: '1 / 1', color: 'var(--text-secondary)' }}>
                <Icon name="library" size={18} />Médiathèque
              </button>
            </div>
            {v.removeMedia.length > 0 && (
              <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{v.removeMedia.length} média(s) retiré(s) · <button type="button" className="underline" onClick={() => set({ removeMedia: [] })}>rétablir</button></div>
            )}

            {showLibrary && (
              <div className="flex flex-col gap-2.5 p-3 rounded-lg" style={{ border: '1px solid var(--border)', background: 'var(--bg-elevated)' }}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold">Médiathèque</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>un clic pour ajouter</span>
                  <div className="ml-auto flex gap-1.5 flex-wrap">
                    <button type="button" onClick={() => setLibTag('')} className="text-[11px] px-2.5 py-1 rounded-full" style={!libTag ? btnPrimary : btnSecondary}>Tous</button>
                    {topTags.map((t) => <button key={t} type="button" onClick={() => setLibTag(t === libTag ? '' : t)} className="text-[11px] px-2.5 py-1 rounded-full capitalize" style={libTag === t ? btnPrimary : btnSecondary}>{t}</button>)}
                  </div>
                </div>
                <input type="search" value={libQ} onChange={(e) => setLibQ(e.target.value)} placeholder="Rechercher : logo, Goyave, enfance…" aria-label="Rechercher un visuel"
                  className="text-sm px-3 py-2 rounded-md outline-none" style={{ ...input, background: 'var(--bg-surface)' }} />
                {libFiltered.length === 0
                  ? <div className="text-xs p-3 text-center" style={{ color: 'var(--text-muted)' }}>{library.length === 0 ? 'La médiathèque est vide : ajoutez des visuels dans l’onglet Médiathèque.' : 'Aucun visuel ne correspond.'}</div>
                  : (
                    <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                      {libFiltered.map((m) => {
                        const on = v.libraryIds.includes(m.id)
                        return (
                          <button key={m.id} type="button" onClick={() => toggleLib(m)} aria-pressed={on} title={`${m.name}${m.tags.length ? ' · ' + m.tags.join(', ') : ''}`}
                            className="relative rounded-md overflow-hidden text-left p-0" style={{ border: on ? '2px solid var(--accent-press)' : '1px solid var(--border)', background: 'var(--bg-surface)' }}>
                            <LibraryThumb m={m} />
                            <span className="block text-[10px] px-1.5 py-1 truncate" style={{ color: 'var(--text-secondary)' }}>{m.name}</span>
                            {on && <span className="absolute top-1 right-1 w-5 h-5 rounded-full inline-flex items-center justify-center" style={{ background: 'var(--accent-press)', color: '#fff' }}><Icon name="check" size={11} stroke={3} /></span>}
                          </button>
                        )
                      })}
                    </div>
                  )}
                <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{library.length} visuel{library.length > 1 ? 's' : ''} · gérés dans l’onglet Médiathèque</div>
              </div>
            )}
          </div>

          {/* Options */}
          <div className="rounded-lg" style={{ border: '1px solid var(--border)' }}>
            <button type="button" onClick={() => setShowOptions((s) => !s)} aria-expanded={showOptions} className="w-full text-left text-xs font-semibold px-3.5 py-3" style={{ color: 'var(--text-secondary)' }}>
              {showOptions ? '▾' : '▸'} Options : réseaux cibles, demandeur, date, lieu, consignes, validité du lien
            </button>
            {showOptions && (
              <div className="grid sm:grid-cols-2 gap-3 px-3.5 pb-3.5">
                <input value={v.networks.join(', ')} onChange={(e) => set({ networks: e.target.value.split(/[,;\n]+/).map((x) => x.trim()).filter(Boolean) })} placeholder="Réseaux cibles (Facebook, Instagram…)" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                <input value={v.requester} onChange={(e) => set({ requester: e.target.value })} placeholder="Demandeur / service" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                <input value={v.scheduled_for} onChange={(e) => set({ scheduled_for: e.target.value })} placeholder="Date / heure souhaitée" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                <input value={v.location} onChange={(e) => set({ location: e.target.value })} placeholder="Lieu" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                <input value={v.requester_email} onChange={(e) => set({ requester_email: e.target.value })} placeholder="E-mail du demandeur" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                <input value={v.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="Consignes pour le validateur" className="text-sm p-2.5 rounded-md outline-none" style={input} />
                {mode === 'create' && (
                  <>
                    <label className="text-xs flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>Validité du lien (heures)
                      <input type="number" min={1} max={720} value={v.ttl_hours} onChange={(e) => set({ ttl_hours: Number(e.target.value) || 72 })} className="text-sm p-1.5 rounded-md w-24 outline-none" style={input} />
                    </label>
                    <label className="text-xs flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                      <input type="checkbox" checked={v.notify} onChange={(e) => set({ notify: e.target.checked })} />Envoyer le lien aux validateurs (Telegram)
                    </label>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 px-6 py-4 flex-wrap" style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
          <span className="text-[11px] flex-1 min-w-[200px]" style={{ color: 'var(--text-muted)' }}>
            {progress || (mode === 'create' ? 'Les médias partent un par un ; le lien n’est envoyé qu’une fois tout en place.' : 'Le lien déjà envoyé reste valable et affiche la version modifiée.')}
          </span>
          {mode === 'create' && onDraft && (
            <button type="button" disabled={!canSubmit} onClick={() => onDraft(v)} className="text-sm px-3.5 py-2.5 rounded-md" style={btnSecondary}>Enregistrer sans envoyer</button>
          )}
          {mode === 'edit' && pub?.status !== 'approved' && pub?.status !== 'publish_failed' && (
            <button type="button" disabled={!canSubmit} onClick={() => onSubmit(v, true)} className="text-sm px-3.5 py-2.5 rounded-md" style={btnSecondary}>Enregistrer et renvoyer un lien</button>
          )}
          <button type="button" disabled={!canSubmit} onClick={() => onSubmit(v, false)} className="text-sm font-semibold px-4 py-2.5 rounded-md inline-flex items-center gap-2" style={{ ...btnPrimary, opacity: canSubmit ? 1 : 0.5 }}>
            <Icon name={mode === 'create' ? 'send' : 'check'} />{busy ? 'Envoi…' : mode === 'create' ? 'Soumettre à validation' : 'Enregistrer'}
          </button>
        </div>
      </aside>
    </div>
  )
}
