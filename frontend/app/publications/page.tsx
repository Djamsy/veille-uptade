'use client'

/**
 * Espace Publications — adresse isolée (/publications), hors menu, thème clair.
 * Réservé aux admins (AuthGuard), affilié au site de veille (bandeau + retour).
 *
 * Flux en trois colonnes (À valider · Validées à publier · Publiées), panneau latéral de
 * soumission / modification avec médiathèque, onglets Médiathèque et Réglages.
 * Le lien de validation n'est affiché qu'une seule fois, au moment de sa création :
 * le serveur n'en conserve que l'empreinte.
 */

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../components/AuthGuard'
import {
  fetchPubValidationStatus, fetchPendingPublications, fetchPendingPublication, createPendingPublication,
  updatePendingPublication, regeneratePublicationLink, revokePublicationLink, cancelPendingPublication,
  publishPendingPublication, deletePendingPublication, syncPublicationSheet, checkPublicationsOnSocial,
  notifyPublicationLink, fetchLibrary, apiErrorMessage,
  type PendingPublication, type PubIssuedLink, type LibraryMedia,
} from '../../lib/api'
import { displayUrl, isVideoUrl, mediaName } from '../../lib/media'
import { Shell, type Tab } from './_components/Shell'
import { FlowBoard } from './_components/FlowBoard'
import { SubmitPanel, type SubmitValues } from './_components/SubmitPanel'
import { LibraryTab } from './_components/LibraryTab'
import { SettingsTab, statusProblems, type PubStatus } from './_components/SettingsTab'
import { Badge, Icon, btnPositive, btnPrimary, btnSecondary, card, fmt, label } from './_components/common'

export default function PublicationsSpace() {
  const { user, loading: authLoading } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [tab, setTab] = useState<Tab>('flux')
  const [status, setStatus] = useState<PubStatus | null>(null)
  const [pubs, setPubs] = useState<PendingPublication[]>([])
  const [library, setLibrary] = useState<LibraryMedia[]>([])
  const [libTags, setLibTags] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [progress, setProgress] = useState('')

  const [panel, setPanel] = useState<{ mode: 'create' | 'edit'; pub?: PendingPublication } | null>(null)
  const [issued, setIssued] = useState<PubIssuedLink | null>(null)
  const [detail, setDetail] = useState<PendingPublication | null>(null)
  const [publishTarget, setPublishTarget] = useState<PendingPublication | null>(null)
  const [publishFile, setPublishFile] = useState<File | null>(null)

  const flash = (m: string) => { setMsg(m); setErr(''); setTimeout(() => setMsg(''), m.length > 120 ? 30000 : 8000) }
  const fail = (e: unknown, ctx: string) => { setErr(apiErrorMessage(e, ctx)); setMsg('') }

  const load = useCallback(async () => {
    if (!isAdmin) return
    setLoading(true)
    try {
      const [s, p, l] = await Promise.all([fetchPubValidationStatus(), fetchPendingPublications(undefined, 300), fetchLibrary()])
      setStatus(s); setPubs(p.publications); setLibrary(l.media); setLibTags(l.tags)
    } catch (e) { fail(e, 'chargement') } finally { setLoading(false) }
  }, [isAdmin])
  useEffect(() => { load() }, [load])

  const reloadLibrary = useCallback(async () => { try { const l = await fetchLibrary(); setLibrary(l.media); setLibTags(l.tags) } catch (e) { fail(e, 'médiathèque') } }, [])

  const run = async (key: string, fn: () => Promise<unknown>, okMsg: string, ctx: string) => {
    setBusy(key)
    try { await fn(); flash(okMsg); await load() } catch (e) { fail(e, ctx) } finally { setBusy('') }
  }
  const copy = async (txt: string) => { try { await navigator.clipboard.writeText(txt); flash('Lien copié dans le presse-papiers') } catch { /* ignore */ } }

  // ── Soumission / modification (médias un par un) ──
  const uploadFiles = async (id: string, files: File[]) => {
    const failed: string[] = []
    let ok = 0
    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      setProgress(`Envoi du média ${i + 1}/${files.length} (${f.name}, ${(f.size / 1048576).toFixed(1)} Mo)…`)
      try { await updatePendingPublication(id, {}, { files: [f] }); ok++ }
      catch (e) { failed.push(`${f.name} : ${(e as { detail?: string })?.detail || apiErrorMessage(e, 'média')}`) }
    }
    setProgress('')
    return { ok, failed }
  }

  const onSubmit = async (v: SubmitValues, resend: boolean, draftOnly = false) => {
    setBusy('submit')
    try {
      if (panel?.mode === 'create') {
        const notify = draftOnly ? false : v.notify
        const r = await createPendingPublication({
          title: v.title, text: v.text, networks: v.networks, scheduled_for: v.scheduled_for, location: v.location,
          requester: v.requester, requester_email: v.requester_email, notes: v.notes, ttl_hours: v.ttl_hours,
          notify: v.files.length ? false : notify, library_ids: v.libraryIds,
        })
        const up = await uploadFiles(r.id, v.files)
        if (v.files.length && notify) { try { await notifyPublicationLink(r.id, r.url) } catch { /* lien affiché de toute façon */ } }
        setPanel(null); setIssued(r)
        const m = `${draftOnly ? 'Enregistrée sans envoi' : 'Soumise à validation'}${up.ok + v.libraryIds.length ? ` avec ${up.ok + v.libraryIds.length} média(s)` : ''} — ${notify ? 'lien envoyé aux validateurs, ' : ''}copiez le lien ci-dessous, il ne sera plus affiché.`
        if (up.failed.length) setErr(`${m} ⚠️ ${up.failed.length} média(s) non envoyé(s) : ${up.failed.join(' | ')}`); else flash(m)
      } else if (panel?.pub) {
        const id = panel.pub.id
        const r = await updatePendingPublication(id, {
          title: v.title, text: v.text, networks: v.networks, scheduled_for: v.scheduled_for, location: v.location,
          requester: v.requester, requester_email: v.requester_email, notes: v.notes,
        }, { removeMedia: v.removeMedia, libraryIds: v.libraryIds })
        const up = await uploadFiles(id, v.files)
        const changed = Array.from(new Set([...r.changed, ...(up.ok ? ['media+'] : [])]))
        let m = changed.length ? `Modifiée (${changed.join(', ')})` : 'Aucun changement'
        if (r.revalidation) { const l = await regeneratePublicationLink(id, undefined, true); setIssued(l); m += ' · texte modifié après validation : renvoyée en validation, nouveau lien envoyé' }
        else if (resend) { const l = await regeneratePublicationLink(id, undefined, true); setIssued(l); m += ' · nouveau lien envoyé aux validateurs' }
        setPanel(null)
        if (up.failed.length) setErr(`${m} ⚠️ ${up.failed.join(' | ')}`); else flash(m)
      }
      await load()
    } catch (e) {
      setProgress('')
      const { status: st, detail } = (e as { status?: number; detail?: string }) ?? {}
      if (st === 409) setErr('Cette publication a déjà été traitée, elle ne peut plus être modifiée.')
      else if (st === 502 || st === 503) setErr(`Médias : ${detail || 'hébergement échoué — voir Réglages.'}`)
      else fail(e, panel?.mode === 'create' ? 'soumission' : 'modification')
    } finally { setBusy('') }
  }

  // ── Actions des cartes ──
  const actions = {
    edit: (p: PendingPublication) => setPanel({ mode: 'edit', pub: p }),
    detail: async (p: PendingPublication) => { try { setDetail(await fetchPendingPublication(p.id)) } catch (e) { fail(e, 'détail') } },
    resend: (p: PendingPublication) => run(`resend-${p.id}`, async () => { const l = await regeneratePublicationLink(p.id, undefined, true); setIssued(l) }, 'Nouveau lien envoyé aux validateurs — l’ancien est invalidé', 'envoi du lien'),
    newLink: (p: PendingPublication) => run(`token-${p.id}`, async () => { const l = await regeneratePublicationLink(p.id); setIssued(l); await copy(l.url) }, 'Nouveau lien généré et copié — l’ancien est invalidé', 'génération du lien'),
    revoke: (p: PendingPublication) => run(`revoke-${p.id}`, () => revokePublicationLink(p.id), 'Lien révoqué', 'révocation'),
    cancel: (p: PendingPublication) => { if (confirm('Annuler cette demande ?')) run(`cancel-${p.id}`, () => cancelPendingPublication(p.id), 'Demande annulée', 'annulation') },
    remove: (p: PendingPublication) => { if (confirm('Supprimer définitivement ? L’historique sera perdu.')) run(`delete-${p.id}`, () => deletePendingPublication(p.id), 'Supprimée', 'suppression') },
    publish: (p: PendingPublication) => { setPublishFile(null); setPublishTarget(p) },
  }

  const problems = statusProblems(status)
  const pending = pubs.filter((p) => p.status === 'pending' || p.status === 'expired').length
  const toPublish = pubs.filter((p) => p.status === 'approved' || p.status === 'publish_failed').length

  // ── Gardes ──
  if (authLoading) return <Shell><div className="min-h-[60vh] flex items-center justify-center"><div className="font-mono text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>Chargement…</div></div></Shell>
  if (!isAdmin) {
    return (
      <Shell>
        <div className="min-h-[60vh] flex items-center justify-center p-4">
          <div className="p-8 max-w-md w-full text-center elev-card" style={card}>
            <h2 className="text-lg font-semibold mb-2">Accès restreint</h2>
            <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>Cet espace est réservé aux administrateurs de Veille Média.</p>
            <a href="/auth/login?next=%2Fpublications" className="btn-primary inline-block px-5 py-2.5 text-sm">Se connecter</a>
          </div>
        </div>
      </Shell>
    )
  }

  const alert = problems.length > 0 && tab !== 'reglages' ? (
    <div className="relative z-10 flex items-center gap-3 px-6 py-2.5 text-sm" style={{ background: 'var(--warn-soft)', borderBottom: '1px solid var(--border)', color: 'var(--warning)' }}>
      <Icon name="warn" /><span><strong>{problems[0]}</strong>{problems.length > 1 ? ` · et ${problems.length - 1} autre(s) point(s)` : ''}</span>
      <button type="button" className="ml-auto font-semibold underline" onClick={() => setTab('reglages')}>Voir les réglages</button>
    </div>
  ) : null

  return (
    <Shell user={user?.name || user?.email} tab={tab} onTab={setTab} alert={alert}>
      <main className="relative z-10 flex-1 p-4 lg:p-8">
        <div className="max-w-[1400px] mx-auto animate-fade-in flex flex-col gap-5">

          {(msg || err) && (
            <div className="px-4 py-2.5 rounded-md text-sm" style={{ background: err ? 'var(--crit-soft)' : 'var(--ok-soft)', color: err ? 'var(--negative)' : 'var(--text)', border: '1px solid var(--border)' }}>{err || msg}</div>
          )}
          {progress && <div className="px-4 py-2 rounded-md text-sm animate-pulse" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>{progress}</div>}

          {issued && (
            <div className="p-4 elev-card" style={{ ...card, borderColor: 'var(--caution)' }}>
              <div className={`${label} mb-2`} style={{ color: 'var(--caution)' }}>Lien de validation — affiché une seule fois</div>
              <div className="flex gap-2 items-center flex-wrap">
                <code className="text-xs break-all flex-1 p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>{issued.url}</code>
                <button type="button" className="text-xs font-semibold px-3 py-2 rounded-md" style={btnPrimary} onClick={() => copy(issued.url)}>Copier</button>
                <button type="button" className="text-xs underline" style={{ color: 'var(--text-muted)' }} onClick={() => setIssued(null)}>Fermer</button>
              </div>
              <p className="text-[11px] mt-2 m-0" style={{ color: 'var(--text-muted)' }}>Expire le {fmt(issued.expires_at)}. Lien personnel : le serveur n’en garde que l’empreinte.</p>
            </div>
          )}

          {tab === 'flux' && (
            <>
              <div className="flex items-end gap-4 flex-wrap">
                <div>
                  <h1 className="m-0 font-serif italic font-medium text-3xl tracking-tight">Publications</h1>
                  <p className="m-0 mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                    {pending} à valider · {toPublish} à publier{status?.social_check?.last?.last_run ? ` · réseaux vérifiés ${fmt(status.social_check.last.last_run)}` : ''}
                  </p>
                </div>
                <div className="ml-auto flex gap-2 flex-wrap">
                  <button type="button" className="text-sm px-3.5 py-2.5 rounded-md inline-flex items-center gap-2" style={btnSecondary} disabled={busy === 'sync' || !status?.sheet.configured}
                    title={status?.sheet.configured ? 'Lire le planning Google maintenant' : 'Planning Google non configuré'}
                    onClick={() => run('sync', async () => {
                      const r = await syncPublicationSheet()
                      if (!r.ok) throw Object.assign(new Error(r.error), { status: 400, detail: r.error })
                      const videos = (r.created ?? []).filter((c) => c.kind === 'video').length
                      const reasons = r.skipped_reasons ? Object.entries(r.skipped_reasons).filter(([k]) => k !== 'ligne_vide').map(([k, v]) => `${k} ×${v}`).join(', ') : ''
                      flash(`Planning lu (${r.tabs?.length ?? 0} onglet(s)) : ${r.created?.length ?? 0} créée(s) dont ${videos} vidéo(s)${reasons ? ` · ignorées : ${reasons}` : ''}${r.errors?.length ? ` · ${r.errors.length} erreur(s) : ${r.errors.slice(0, 3).map((e) => `${e.tab ?? ''} L${e.row ?? '?'} ${e.error}`).join(' | ')}` : ''}`)
                    }, 'Import terminé', 'import du planning')}>
                    <Icon name="refresh" />{busy === 'sync' ? 'Lecture…' : 'Lire le planning'}
                  </button>
                  <button type="button" className="text-sm px-3.5 py-2.5 rounded-md inline-flex items-center gap-2" style={btnSecondary} disabled={busy === 'social'}
                    onClick={() => run('social', async () => {
                      const r = await checkPublicationsOnSocial()
                      const nf = r.not_found.length ? ` · non trouvées : ${r.not_found.slice(0, 4).map((e) => `${e.title}${e.days_since_decision != null ? ` (validée il y a ${e.days_since_decision} j)` : ''}`).join(' | ')}` : ''
                      flash(`${r.posts_examined} post(s) des comptes examinés · ${r.checked} vérifiée(s) · ${r.newly_detected.length} constatée(s) publiée(s)${nf}${r.warning ? ` · ${r.warning}` : ''}`)
                    }, 'Vérification terminée', 'vérification sur les réseaux')}>
                    <Icon name="radar" />{busy === 'social' ? 'Vérification…' : 'Vérifier sur les réseaux'}
                  </button>
                  <button type="button" className="text-sm font-semibold px-4 py-2.5 rounded-md inline-flex items-center gap-2" style={btnPrimary} onClick={() => setPanel({ mode: 'create' })}>
                    <Icon name="plus" stroke={2.4} />Nouvelle publication
                  </button>
                </div>
              </div>
              {loading ? <div className="font-mono text-xs animate-pulse py-10 text-center" style={{ color: 'var(--text-muted)' }}>Déchiffrement…</div>
                : <FlowBoard pubs={pubs} busy={busy} actions={actions} />}
            </>
          )}

          {tab === 'mediatheque' && <LibraryTab library={library} tags={libTags} onChanged={reloadLibrary} flash={flash} fail={fail} />}
          {tab === 'reglages' && <SettingsTab status={status} />}
        </div>
      </main>

      {panel && (
        <SubmitPanel mode={panel.mode} pub={panel.pub} library={library} tags={libTags} onClose={() => setPanel(null)}
          onSubmit={(v, resend) => onSubmit(v, resend)} onDraft={(v) => onSubmit(v, false, true)} busy={busy === 'submit'} progress={progress} />
      )}

      {/* Publication (fichier joint facultatif) */}
      {publishTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(24,24,27,0.45)' }} onClick={() => setPublishTarget(null)}>
          <div className="theme-clair max-w-lg w-full p-6 elev-card" style={card} onClick={(e) => e.stopPropagation()}>
            <div className={`${label} mb-1`} style={{ color: 'var(--text-muted)' }}>Publier sur Buffer</div>
            <h2 className="font-serif text-xl italic mb-3">{publishTarget.payload.title || '(sans titre)'}</h2>
            {(publishTarget.payload.links?.length ?? 0) > 0 && (publishTarget.payload.media_urls?.length ?? 0) === 0 && (
              <div className="text-xs mb-3 p-3 rounded-md" style={{ background: 'var(--warn-soft)', color: 'var(--warning)' }}>
                Cette publication n’a que des liens (WeTransfer / Purevision), pas de fichier direct. Téléchargez la vidéo puis joignez-la ci-dessous, sinon le post partira sans média.
                <div className="mt-1 space-y-0.5">{publishTarget.payload.links!.map((u) => <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="underline block break-all" style={{ color: 'var(--accent-link)' }}>{u}</a>)}</div>
              </div>
            )}
            {(publishTarget.payload.media_urls?.length ?? 0) > 0 && (
              <div className="flex gap-1.5 mb-3 flex-wrap">
                {publishTarget.payload.media_urls.slice(0, 6).map((u) => (
                  <div key={u} className="w-14 h-14 rounded overflow-hidden" style={{ border: '1px solid var(--border)' }}>
                    {isVideoUrl(u) ? <video src={displayUrl(u)} className="w-full h-full object-cover" muted /> : // eslint-disable-next-line @next/next/no-img-element
                      <img src={displayUrl(u, 200)} alt="" title={mediaName(u)} className="w-full h-full object-cover" />}
                  </div>
                ))}
              </div>
            )}
            <label className="text-xs block mb-1" style={{ color: 'var(--text-secondary)' }}>Fichier à joindre en plus (image ou vidéo, facultatif)</label>
            <input type="file" accept="image/*,video/*" className="text-xs mb-4 w-full" onChange={(e) => setPublishFile(e.target.files?.[0] ?? null)} />
            {publishFile && <div className="text-[11px] mb-3" style={{ color: 'var(--text-muted)' }}>{publishFile.name} · {(publishFile.size / 1048576).toFixed(1)} Mo</div>}
            <div className="flex gap-2">
              <button type="button" className="text-sm font-semibold px-4 py-2.5 rounded-md" style={btnPositive} disabled={busy === `publish-${publishTarget.id}`}
                onClick={() => { const t = publishTarget; setPublishTarget(null); run(`publish-${t.id}`, () => publishPendingPublication(t.id, publishFile ?? undefined), 'Publication envoyée sur Buffer', 'publication') }}>
                {publishFile ? 'Publier avec le fichier' : 'Publier'}
              </button>
              <button type="button" className="text-sm underline" style={{ color: 'var(--text-muted)' }} onClick={() => setPublishTarget(null)}>Annuler</button>
            </div>
          </div>
        </div>
      )}

      {/* Détail */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(24,24,27,0.45)' }} onClick={() => setDetail(null)}>
          <div className="theme-clair max-w-2xl w-full max-h-[85vh] overflow-auto p-6 elev-card" style={card} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <div className={`${label} mb-1`} style={{ color: 'var(--text-muted)' }}>Détail · {detail.source === 'sheet' ? `${detail.sheet_tab ?? 'planning'} · ligne ${detail.sheet_row}` : 'saisie manuelle'}</div>
                <h2 className="font-serif text-2xl italic">{detail.payload.title || '(sans titre)'}</h2>
              </div>
              <Badge status={detail.status} />
            </div>
            <p className="text-sm whitespace-pre-wrap mb-3" style={{ color: 'var(--text-secondary)' }}>{detail.payload.text}</p>
            {detail.payload.original_text && (
              <details className="text-xs mb-3"><summary style={{ color: 'var(--text-muted)' }}>Texte d’origine (modifié par {detail.payload.edited_by})</summary>
                <p className="whitespace-pre-wrap mt-1" style={{ color: 'var(--text-muted)' }}>{detail.payload.original_text}</p></details>
            )}
            {(detail.payload.media_urls?.length ?? 0) > 0 && (
              <div className="flex gap-1.5 mb-3 flex-wrap">
                {detail.payload.media_urls.map((u) => (
                  <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="w-16 h-16 rounded overflow-hidden" style={{ border: '1px solid var(--border)' }}>
                    {isVideoUrl(u) ? <video src={displayUrl(u)} className="w-full h-full object-cover" muted /> : // eslint-disable-next-line @next/next/no-img-element
                      <img src={displayUrl(u, 200)} alt="" title={mediaName(u)} className="w-full h-full object-cover" />}
                  </a>
                ))}
              </div>
            )}
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
              <dt style={{ color: 'var(--text-muted)' }}>Demandeur</dt><dd>{detail.payload.requester || '—'}{detail.payload.requester_email && ` · ${detail.payload.requester_email}`}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Date · lieu</dt><dd>{[detail.payload.scheduled_for, detail.payload.location].filter(Boolean).join(' · ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Prestation</dt><dd>{[detail.payload.service, detail.payload.provider].filter(Boolean).join(' · ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Réseaux</dt><dd>{detail.payload.networks.join(', ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Liens</dt><dd className="break-all">{(detail.payload.links ?? []).length ? detail.payload.links!.map((u) => <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="underline block" style={{ color: 'var(--accent-link)' }}>{u}</a>) : '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Consignes</dt><dd>{detail.payload.notes || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Lien</dt><dd>{detail.token.active && !detail.token.expired ? `actif, expire le ${fmt(detail.token.expires_at)}` : detail.token.revoked ? 'révoqué' : 'expiré ou inexistant'}</dd>
              {detail.decision && <><dt style={{ color: 'var(--text-muted)' }}>Décision</dt><dd>{detail.decision.decision === 'approve' ? 'Validée' : 'Refusée'} par {detail.decision.by} le {fmt(detail.decision.at)}{detail.decision.comment && ` — « ${detail.decision.comment} »`}</dd></>}
              {detail.publish && <><dt style={{ color: 'var(--text-muted)' }}>Publication</dt><dd>{detail.publish.via === 'detected_on_social' ? <>Constatée sur {detail.publish.platform} ({detail.publish.how}) le {fmt(detail.publish.published_at)} — <a href={detail.publish.url || undefined} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: 'var(--accent-link)' }}>voir le post</a></> : detail.publish.ok ? `OK sur ${detail.publish.platforms} réseau(x) le ${fmt(detail.publish.published_at)}` : `Échec : ${detail.publish.error}`}</dd></>}
              {detail.seen && <><dt style={{ color: 'var(--text-muted)' }}>Réseaux</dt><dd>
                {detail.seen.matched ? 'Trouvée' : 'Non trouvée'} (vérifié le {fmt(detail.seen.checked_at)}, seuil {Math.round(detail.seen.threshold * 100)} %)
                {detail.seen.candidates.length > 0 && <ul className="mt-1 space-y-0.5 pl-0 list-none">{detail.seen.candidates.map((c) => <li key={c.url + c.score} className="text-[11px]"><a href={c.url || undefined} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: 'var(--accent-link)' }}>{c.platform}</a> · {Math.round(c.score * 100)} % · {c.how} · <span style={{ color: 'var(--text-muted)' }}>{c.excerpt}</span></li>)}</ul>}
              </dd></>}
            </dl>
            <div className={`${label} mb-2`} style={{ color: 'var(--text-muted)' }}>Journal</div>
            <ul className="text-[11px] font-mono space-y-1 pl-0 list-none" style={{ color: 'var(--text-muted)' }}>
              {(detail.audit ?? []).map((a, i) => <li key={i}>{fmt(a.at)} · {a.action}{a.actor && ` · ${a.actor}`}{a.detail && ` · ${a.detail}`}</li>)}
            </ul>
            <div className="mt-4 flex gap-2 justify-end">
              {(detail.status === 'pending' || detail.status === 'expired' || detail.status === 'approved' || detail.status === 'publish_failed') && <button type="button" className="text-sm px-3.5 py-2 rounded-md" style={btnSecondary} onClick={() => { const p = detail; setDetail(null); setPanel({ mode: 'edit', pub: p }) }}>Modifier</button>}
              <button type="button" className="text-sm underline" style={{ color: 'var(--text-muted)' }} onClick={() => setDetail(null)}>Fermer</button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  )
}
