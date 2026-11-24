'use client'

import { useMemo, useState } from 'react'
import { addLibraryFiles, apiErrorMessage, deleteLibraryMedia, updateLibraryMedia, type LibraryMedia } from '../../../lib/api'
import { displayUrl } from '../../../lib/media'
import { Icon, IconButton, btnPrimary, btnSecondary, card, input, timeAgo } from './common'

function Thumb({ m }: { m: LibraryMedia }) {
  const [broken, setBroken] = useState(false)
  if (m.kind === 'video') return <video src={displayUrl(m.url)} className="w-full h-full object-cover" muted preload="metadata" controls />
  if (broken) return <div className="w-full h-full flex items-center justify-center text-xs px-2 text-center" style={{ color: 'var(--text-muted)' }}>{m.name}</div>
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={displayUrl(m.url, 600)} alt="" className="w-full h-full object-cover" loading="lazy" onError={() => setBroken(true)} />
}

function MediaCard({ m, onChanged, flash, fail }: { m: LibraryMedia; onChanged: () => void; flash: (s: string) => void; fail: (e: unknown, c: string) => void }) {
  const [edit, setEdit] = useState(false)
  const [name, setName] = useState(m.name)
  const [tags, setTags] = useState(m.tags.join(', '))
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { await updateLibraryMedia(m.id, { name: name.trim(), tags: tags.split(/[,;]+/).map((t) => t.trim()).filter(Boolean) }); setEdit(false); flash('Visuel mis à jour'); onChanged() }
    catch (e) { fail(e, 'mise à jour du visuel') } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!confirm(`Retirer « ${m.name} » de la médiathèque ? Les publications qui l'utilisent déjà le gardent.`)) return
    setBusy(true)
    try { await deleteLibraryMedia(m.id); flash('Visuel retiré'); onChanged() } catch (e) { fail(e, 'suppression') } finally { setBusy(false) }
  }
  const size = m.bytes ? `${(m.bytes / 1024).toFixed(0)} Ko` : ''
  return (
    <article className="flex flex-col overflow-hidden elev-card" style={card}>
      <div style={{ aspectRatio: '4 / 3', background: 'var(--bg-elevated)' }}><Thumb m={m} /></div>
      <div className="flex flex-col gap-1.5 p-3">
        {edit ? (
          <>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="text-sm p-2 rounded-md outline-none" style={input} aria-label="Nom du visuel" />
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Étiquettes, séparées par des virgules" className="text-xs p-2 rounded-md outline-none" style={input} aria-label="Étiquettes" />
            <div className="flex gap-2 mt-1">
              <button type="button" disabled={busy} onClick={save} className="text-xs px-3 py-1.5 rounded-md" style={btnPrimary}>Enregistrer</button>
              <button type="button" onClick={() => { setEdit(false); setName(m.name); setTags(m.tags.join(', ')) }} className="text-xs px-3 py-1.5 rounded-md" style={btnSecondary}>Annuler</button>
            </div>
          </>
        ) : (
          <>
            <strong className="text-sm truncate" title={m.name}>{m.name}</strong>
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              {m.kind === 'video' ? 'Vidéo' : m.url.toLowerCase().includes('.png') ? 'PNG' : 'Image'}{m.width && m.height ? ` · ${m.width} × ${m.height}` : ''}{size ? ` · ${size}` : ''} · utilisé {m.uses} fois
            </span>
            <div className="flex gap-1 flex-wrap min-h-[18px]">
              {m.tags.map((t) => <span key={t} className="text-[10px] px-1.5 py-0.5 rounded capitalize" style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>{t}</span>)}
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <button type="button" onClick={() => setEdit(true)} className="text-[11px] px-2.5 py-1.5 rounded-md inline-flex items-center gap-1" style={btnSecondary}><Icon name="edit" size={12} />Nom et étiquettes</button>
              <span className="ml-auto text-[10px]" style={{ color: 'var(--text-muted)' }} title={m.uploaded_by}>{timeAgo(m.created_at)}</span>
              <IconButton name="trash" title="Retirer de la médiathèque" onClick={remove} disabled={busy} style={{ color: 'var(--negative)' }} />
            </div>
          </>
        )}
      </div>
    </article>
  )
}

export function LibraryTab({ library, tags, onChanged, flash, fail }: {
  library: LibraryMedia[]; tags: Record<string, number>; onChanged: () => void; flash: (s: string) => void; fail: (e: unknown, c: string) => void
}) {
  const [tag, setTag] = useState('')
  const [q, setQ] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [newTags, setNewTags] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')

  const shown = useMemo(() => library.filter((m) => (!tag || m.tags.includes(tag)) && (!q || (m.name + ' ' + m.tags.join(' ')).toLowerCase().includes(q.toLowerCase()))), [library, tag, q])

  const upload = async () => {
    if (!files.length) return
    setBusy(true)
    const t = newTags.split(/[,;]+/).map((x) => x.trim()).filter(Boolean)
    let ok = 0
    const failed: string[] = []
    for (let i = 0; i < files.length; i++) {
      setProgress(`Dépôt ${i + 1}/${files.length} (${files[i].name}, ${(files[i].size / 1048576).toFixed(1)} Mo)…`)
      try { const r = await addLibraryFiles([files[i]], t); ok += r.added.length; r.errors.forEach((e) => failed.push(`${e.file} : ${e.error}`)) }
      catch (e) { failed.push(`${files[i].name} : ${(e as { detail?: string })?.detail || apiErrorMessage(e, 'dépôt')}`) }
    }
    setProgress(''); setBusy(false); setFiles([])
    if (failed.length) fail(Object.assign(new Error('x'), { status: 502, detail: failed.join(' | ') }), `dépôt (${ok} réussi(s))`)
    else flash(`${ok} visuel${ok > 1 ? 's' : ''} ajouté${ok > 1 ? 's' : ''} à la médiathèque${t.length ? ` (${t.join(', ')})` : ''}`)
    onChanged()
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end gap-4 flex-wrap">
        <div>
          <h1 className="m-0 font-serif italic font-medium text-3xl tracking-tight">Médiathèque</h1>
          <p className="m-0 mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>{library.length} visuel{library.length > 1 ? 's' : ''} pré-enregistré{library.length > 1 ? 's' : ''} · tout le service peut en ajouter · sélectionnables en un clic dans une publication</p>
        </div>
      </div>

      {/* Dépôt */}
      <div className="flex flex-col gap-3 p-4 elev-card" style={card}>
        <div className="flex items-center gap-3 flex-wrap">
          <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold cursor-pointer" style={btnPrimary}>
            <input type="file" accept="image/*,video/*" multiple className="hidden" onChange={(e) => { setFiles((cur) => [...cur, ...Array.from(e.target.files ?? [])].slice(0, 25)); e.target.value = '' }} />
            <Icon name="plus" stroke={2.4} />Ajouter des visuels
          </label>
          <input value={newTags} onChange={(e) => setNewTags(e.target.value)} placeholder="Étiquettes pour ce dépôt : logo, bandeau, lieu, élu…" className="text-sm p-2.5 rounded-md outline-none flex-1 min-w-[240px]" style={input} aria-label="Étiquettes" />
          <button type="button" disabled={!files.length || busy} onClick={upload} className="text-sm px-4 py-2.5 rounded-md inline-flex items-center gap-2" style={{ ...btnSecondary, opacity: files.length ? 1 : 0.5 }}>
            <Icon name="upload" />{busy ? 'Dépôt…' : `Déposer${files.length ? ` ${files.length} fichier${files.length > 1 ? 's' : ''}` : ''}`}
          </button>
        </div>
        {files.length > 0 && (
          <div className="flex gap-2 flex-wrap text-[11px]" style={{ color: 'var(--text-secondary)' }}>
            {files.map((f, i) => <span key={f.name + i} className="inline-flex items-center gap-1 px-2 py-1 rounded" style={{ background: 'var(--bg-elevated)' }}>{f.name}<button type="button" aria-label="Retirer" onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}><Icon name="x" size={10} stroke={3} /></button></span>)}
          </div>
        )}
        {progress && <div className="text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>{progress}</div>}
        <p className="m-0 text-[11px]" style={{ color: 'var(--text-muted)' }}>PNG (transparence conservée), JPG, MP4 · images recompressées à 1920 px · nommez et étiquetez ensuite sur chaque carte.</p>
      </div>

      {/* Filtres */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <button type="button" onClick={() => setTag('')} className="text-xs px-3 py-1.5 rounded-full" style={!tag ? btnPrimary : btnSecondary}>Tous · {library.length}</button>
        {Object.entries(tags).slice(0, 12).map(([t, n]) => (
          <button key={t} type="button" onClick={() => setTag(t === tag ? '' : t)} className="text-xs px-3 py-1.5 rounded-full capitalize" style={tag === t ? btnPrimary : btnSecondary}>{t} · {n}</button>
        ))}
        <div className="ml-auto relative">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un visuel" aria-label="Rechercher" className="text-sm pl-8 pr-3 py-2 rounded-md outline-none min-w-[220px]" style={input} />
          <span className="absolute left-2.5 top-2.5" style={{ color: 'var(--text-muted)' }}><Icon name="search" /></span>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="p-10 text-center text-sm rounded-lg" style={{ border: '1px dashed var(--border-strong)', color: 'var(--text-muted)' }}>
          {library.length === 0 ? 'La médiathèque est vide. Déposez vos logos, bandeaux et visuels récurrents : ils seront proposés dans chaque nouvelle publication.' : 'Aucun visuel ne correspond à ce filtre.'}
        </div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
          {shown.map((m) => <MediaCard key={m.id} m={m} onChanged={onChanged} flash={flash} fail={fail} />)}
        </div>
      )}
    </div>
  )
}
