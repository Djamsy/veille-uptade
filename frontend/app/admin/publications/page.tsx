'use client'

/**
 * Admin — Publications pour validation.
 *
 * Suivi des demandes (contenu chiffré côté serveur, déchiffré à la volée pour l'admin),
 * création manuelle, (ré)génération / révocation des liens à jeton, publication,
 * import immédiat depuis la feuille Google, diagnostic de configuration.
 *
 * Le lien de validation n'est affiché qu'une seule fois, au moment de sa création :
 * le serveur n'en conserve que l'empreinte.
 */

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../../components/Sidebar'
import { useAuth } from '../../../components/AuthGuard'
import {
  fetchPubValidationStatus,
  fetchPendingPublications,
  fetchPendingPublication,
  createPendingPublication,
  regeneratePublicationLink,
  revokePublicationLink,
  cancelPendingPublication,
  publishPendingPublication,
  deletePendingPublication,
  syncPublicationSheet,
  apiErrorMessage,
  PUB_STATUS_LABEL,
  type PendingPublication,
  type PubIssuedLink,
} from '../../../lib/api'

type Status = Awaited<ReturnType<typeof fetchPubValidationStatus>>

const label = 'font-mono text-[10px] uppercase tracking-[0.18em]'
const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }
const input: React.CSSProperties = { background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }

const STATUS_TONE: Record<string, { bg: string; color: string }> = {
  pending: { bg: 'var(--warn-soft)', color: 'var(--warning)' },
  approved: { bg: 'var(--bg-elevated)', color: 'var(--accent-link)' },
  published: { bg: 'var(--bg-elevated)', color: 'var(--positive)' },
  rejected: { bg: 'var(--crit-soft)', color: 'var(--negative)' },
  publish_failed: { bg: 'var(--crit-soft)', color: 'var(--negative)' },
  expired: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' },
  cancelled: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' },
}

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '—')

function Badge({ status }: { status: string }) {
  const t = STATUS_TONE[status] ?? STATUS_TONE.expired
  return (
    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm whitespace-nowrap" style={{ background: t.bg, color: t.color, border: '1px solid var(--border)' }}>
      {PUB_STATUS_LABEL[status] ?? status}
    </span>
  )
}

function Dot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ background: ok ? (warn ? 'var(--caution)' : 'var(--positive)') : 'var(--negative)' }} />
}

export default function AdminPublicationsPage() {
  const { user, loading: authLoading } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [status, setStatus] = useState<Status | null>(null)
  const [pubs, setPubs] = useState<PendingPublication[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [filter, setFilter] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState<string>('')

  const [issued, setIssued] = useState<PubIssuedLink | null>(null)
  const [publishTarget, setPublishTarget] = useState<PendingPublication | null>(null)
  const [publishFile, setPublishFile] = useState<File | null>(null)
  const [detail, setDetail] = useState<PendingPublication | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', text: '', media_urls: '', networks: '', scheduled_for: '', requester: '', requester_email: '', notes: '', ttl_hours: 72, notify: true })

  const flash = (m: string) => { setMsg(m); setErr(''); setTimeout(() => setMsg(''), 5000) }
  const fail = (e: unknown, ctx: string) => { setErr(apiErrorMessage(e, ctx)); setMsg('') }

  const load = useCallback(async () => {
    if (!isAdmin) return
    setLoading(true)
    try {
      const [s, p] = await Promise.all([fetchPubValidationStatus(), fetchPendingPublications(filter || undefined)])
      setStatus(s); setPubs(p.publications); setCounts(p.counts)
    } catch (e) { fail(e, 'chargement') } finally { setLoading(false) }
  }, [isAdmin, filter])

  useEffect(() => { load() }, [load])

  const run = async (key: string, fn: () => Promise<unknown>, okMsg: string, ctx: string) => {
    setBusy(key)
    try { await fn(); flash(okMsg); await load() } catch (e) { fail(e, ctx) } finally { setBusy('') }
  }

  const copy = async (txt: string) => {
    try { await navigator.clipboard.writeText(txt); flash('Lien copié dans le presse-papiers') } catch { /* ignore */ }
  }

  const onCreate = async () => {
    setBusy('create')
    try {
      const r = await createPendingPublication({
        title: form.title, text: form.text,
        media_urls: form.media_urls.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean),
        networks: form.networks.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean),
        scheduled_for: form.scheduled_for, requester: form.requester, requester_email: form.requester_email, notes: form.notes,
        ttl_hours: form.ttl_hours, notify: form.notify,
      })
      setIssued(r); setShowCreate(false)
      setForm({ title: '', text: '', media_urls: '', networks: '', scheduled_for: '', requester: '', requester_email: '', notes: '', ttl_hours: 72, notify: true })
      flash('Publication créée — copiez le lien maintenant, il ne sera plus affiché.')
      await load()
    } catch (e) { fail(e, 'création') } finally { setBusy('') }
  }

  const onRegenerate = async (id: string) => {
    setBusy(`token-${id}`)
    try { const r = await regeneratePublicationLink(id); setIssued(r); flash('Nouveau lien généré — l’ancien est invalidé.'); await load() }
    catch (e) { fail(e, 'génération du lien') } finally { setBusy('') }
  }

  const openDetail = async (id: string) => {
    try { setDetail(await fetchPendingPublication(id)) } catch (e) { fail(e, 'détail') }
  }

  // ── Garde ─────────────────────────────────────────────
  if (authLoading) {
    return (
      <div className="flex"><Sidebar />
        <main className="lg:ml-16 flex-1 min-h-screen flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
        </main>
      </div>
    )
  }
  if (!isAdmin) {
    return (
      <div className="flex"><Sidebar />
        <main className="lg:ml-16 flex-1 min-h-screen flex items-center justify-center p-4">
          <div className="glass-card-static p-8 max-w-md w-full text-center">
            <h2 className="text-lg font-semibold mb-2">Accès restreint</h2>
            <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>Cette page est réservée aux administrateurs.</p>
            <a href="/auth/login" className="btn-primary inline-block px-5 py-2.5 text-sm">Se connecter</a>
          </div>
        </main>
      </div>
    )
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-16 flex-1 p-4 lg:p-6 min-h-screen">
        <div className="max-w-[1400px] mx-auto animate-fade-in">
          {/* En-tête */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
            <div>
              <div className={`${label} mb-2`} style={{ color: 'var(--text-muted)' }}>Système / Publications</div>
              <h1 className="font-serif text-3xl font-medium tracking-tight italic">Publications pour validation</h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                Contenu chiffré au repos (AES-256-GCM) · liens à jeton à usage unique · publication manuelle
              </p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => setShowCreate((v) => !v)}>+ Nouvelle demande</button>
              <button type="button" className="px-4 py-2 text-sm rounded-md" style={{ ...input }} disabled={busy === 'sync' || !status?.sheet.configured}
                title={status?.sheet.configured ? 'Lire le planning Google maintenant' : 'Planning Google non configuré'}
                onClick={() => run('sync', async () => {
                  const r = await syncPublicationSheet()
                  if (!r.ok) throw Object.assign(new Error(r.error), { status: 400 })
                  const videos = (r.created ?? []).filter((c) => c.kind === 'video').length
                  const errs = r.errors?.length ? ` · ${r.errors.length} erreur(s) : ${r.errors.slice(0, 3).map((e) => `${e.tab ?? ''} L${e.row ?? '?'} ${e.error}`).join(' | ')}` : ''
                  flash(`Planning lu (${r.tabs?.length ?? 0} onglet(s)) : ${r.created?.length ?? 0} créée(s) dont ${videos} vidéo(s), ${r.skipped ?? 0} ignorée(s)${errs}`)
                }, 'Import terminé', 'import de la feuille')}>
                {busy === 'sync' ? 'Lecture…' : '⟳ Lire le planning'}
              </button>
            </div>
          </div>

          {(msg || err) && (
            <div className="px-4 py-2 rounded-md text-sm mb-4" style={{ background: err ? 'var(--crit-soft)' : 'var(--bg-elevated)', color: err ? 'var(--negative)' : 'var(--text)', border: '1px solid var(--border)' }}>
              {err || msg}
            </div>
          )}

          {/* Lien fraîchement émis */}
          {issued && (
            <div className="p-4 mb-4 elev-card" style={{ ...card, borderColor: 'var(--caution)' }}>
              <div className={`${label} mb-2`} style={{ color: 'var(--caution)' }}>🔐 Lien de validation — affiché une seule fois</div>
              <div className="flex gap-2 items-center flex-wrap">
                <code className="text-xs break-all flex-1 p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>{issued.url}</code>
                <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={() => copy(issued.url)}>Copier</button>
                <button type="button" className="text-xs underline" style={{ color: 'var(--text-muted)' }} onClick={() => setIssued(null)}>Fermer</button>
              </div>
              <p className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>Expire le {fmt(issued.expires_at)}. Transmettez-le au validateur par un canal sûr ; le serveur ne le conserve pas.</p>
            </div>
          )}

          {/* Création manuelle */}
          {showCreate && (
            <div className="p-5 mb-4 elev-card" style={card}>
              <div className={`${label} mb-3`} style={{ color: 'var(--text-muted)' }}>Nouvelle demande de validation</div>
              <div className="grid md:grid-cols-2 gap-3">
                <input className="text-sm p-2.5 rounded-md outline-none" style={input} placeholder="Titre" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                <input className="text-sm p-2.5 rounded-md outline-none" style={input} placeholder="Demandeur" value={form.requester} onChange={(e) => setForm({ ...form, requester: e.target.value })} />
                <textarea className="text-sm p-2.5 rounded-md outline-none md:col-span-2" style={input} rows={5} placeholder="Texte du post (obligatoire) — #hashtags détectés automatiquement" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
                <textarea className="text-sm p-2.5 rounded-md outline-none" style={input} rows={2} placeholder="URL des médias (une par ligne)" value={form.media_urls} onChange={(e) => setForm({ ...form, media_urls: e.target.value })} />
                <input className="text-sm p-2.5 rounded-md outline-none" style={input} placeholder="Réseaux cibles (Facebook, Instagram…)" value={form.networks} onChange={(e) => setForm({ ...form, networks: e.target.value })} />
                <input className="text-sm p-2.5 rounded-md outline-none" style={input} placeholder="Date souhaitée (texte libre)" value={form.scheduled_for} onChange={(e) => setForm({ ...form, scheduled_for: e.target.value })} />
                <input className="text-sm p-2.5 rounded-md outline-none" style={input} placeholder="E-mail du demandeur" value={form.requester_email} onChange={(e) => setForm({ ...form, requester_email: e.target.value })} />
                <input className="text-sm p-2.5 rounded-md outline-none md:col-span-2" style={input} placeholder="Consignes pour le validateur" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                <label className="text-xs flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                  Validité du lien (heures)
                  <input type="number" min={1} max={720} className="text-sm p-1.5 rounded-md w-24 outline-none" style={input} value={form.ttl_hours} onChange={(e) => setForm({ ...form, ttl_hours: Number(e.target.value) || 72 })} />
                </label>
                <label className="text-xs flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                  <input type="checkbox" checked={form.notify} onChange={(e) => setForm({ ...form, notify: e.target.checked })} />
                  Envoyer le lien aux validateurs (Telegram / e-mail)
                </label>
              </div>
              <div className="flex gap-2 mt-4">
                <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={busy === 'create' || !form.text.trim()} onClick={onCreate}>
                  {busy === 'create' ? 'Création…' : 'Créer et générer le lien'}
                </button>
                <button type="button" className="text-sm underline" style={{ color: 'var(--text-muted)' }} onClick={() => setShowCreate(false)}>Annuler</button>
              </div>
            </div>
          )}

          <div className="grid lg:grid-cols-[1fr_300px] gap-4">
            {/* Liste */}
            <div>
              <div className="flex gap-1 mb-3 p-1 rounded-xl w-fit flex-wrap" style={{ background: 'var(--bg-elevated)' }}>
                {[['', `Toutes (${total})`], ...Object.keys(PUB_STATUS_LABEL).map((k) => [k, `${PUB_STATUS_LABEL[k]} (${counts[k] ?? 0})`])].map(([k, l]) => (
                  <button key={k} type="button" onClick={() => setFilter(k)}
                    className="px-3 py-1.5 text-xs rounded-lg"
                    style={filter === k ? { background: 'var(--bg-surface)', color: 'var(--text)', boxShadow: 'var(--shadow-card)' } : { color: 'var(--text-muted)' }}>
                    {l}
                  </button>
                ))}
              </div>

              {loading ? (
                <div className="font-mono text-xs animate-pulse py-10 text-center" style={{ color: 'var(--text-muted)' }}>Déchiffrement…</div>
              ) : pubs.length === 0 ? (
                <div className="p-8 text-center text-sm elev-card" style={{ ...card, color: 'var(--text-muted)' }}>Aucune publication {filter && `au statut « ${PUB_STATUS_LABEL[filter]} »`}.</div>
              ) : (
                <div className="space-y-2">
                  {pubs.map((p) => {
                    const canLink = p.status === 'pending' || p.status === 'expired'
                    const canPublish = p.status === 'approved' || p.status === 'publish_failed'
                    const b = (k: string) => busy === `${k}-${p.id}`
                    return (
                      <div key={p.id} className="p-4 elev-card" style={card}>
                        <div className="flex items-start gap-3 flex-wrap">
                          <div className="flex-1 min-w-[220px]">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <Badge status={p.status} />
                              <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                                {p.source === 'sheet' ? `${p.sheet_tab ?? 'Planning'} · ligne ${p.sheet_row}` : 'Manuelle'} · {fmt(p.created_at)}
                              </span>
                              {p.token.active && !p.token.expired && <span className="font-mono text-[10px]" style={{ color: 'var(--caution)' }}>🔗 lien actif → {fmt(p.token.expires_at)}</span>}
                            </div>
                            <button type="button" onClick={() => openDetail(p.id)} className="text-left">
                              <div className="font-medium text-sm hover:underline">{p.payload?.title || p.error || '(sans titre)'}</div>
                            </button>
                            <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>{p.payload?.text}</p>
                            <div className="flex gap-3 mt-1.5 font-mono text-[10px] flex-wrap" style={{ color: 'var(--text-muted)' }}>
                              {p.payload?.scheduled_for && <span>📅 {p.payload.scheduled_for}</span>}
                              {p.payload?.location && <span>📍 {p.payload.location}</span>}
                              {p.payload?.requester && <span>👤 {p.payload.requester}</span>}
                              {p.payload?.networks?.length > 0 && <span>📣 {p.payload.networks.join(', ')}</span>}
                              {p.payload?.kind === 'video' && <span style={{ color: 'var(--accent-link)' }}>🎬 vidéo livrée</span>}
                              {p.payload?.media_urls?.length > 0 && <span>🖼 {p.payload.media_urls.length} média(s)</span>}
                              {(p.payload?.links?.length ?? 0) > 0 && <span>🔗 {p.payload.links!.length} lien(s)</span>}
                              {p.decision && <span>{p.decision.decision === 'approve' ? '✓' : '✕'} {p.decision.by}</span>}
                              {p.publish && <span>{p.publish.ok ? `📤 ${p.publish.platforms} réseau(x)` : `⚠️ ${p.publish.error}`}</span>}
                            </div>
                          </div>
                          <div className="flex gap-1.5 flex-wrap">
                            {canLink && <button type="button" className="text-xs px-2.5 py-1.5 rounded-md" style={input} disabled={b('token')} onClick={() => onRegenerate(p.id)}>{b('token') ? '…' : '🔗 Nouveau lien'}</button>}
                            {p.token.active && p.status === 'pending' && <button type="button" className="text-xs px-2.5 py-1.5 rounded-md" style={input} disabled={b('revoke')} onClick={() => run(`revoke-${p.id}`, () => revokePublicationLink(p.id), 'Lien révoqué', 'révocation')}>Révoquer</button>}
                            {canPublish && <button type="button" className="text-xs px-2.5 py-1.5 rounded-md" style={{ background: 'var(--positive)', color: '#fff' }} disabled={b('publish')} onClick={() => { setPublishFile(null); setPublishTarget(p) }}>{b('publish') ? 'Envoi…' : '📤 Publier'}</button>}
                            {(p.status === 'pending' || p.status === 'approved' || p.status === 'expired') && <button type="button" className="text-xs px-2.5 py-1.5 rounded-md" style={input} disabled={b('cancel')} onClick={() => { if (confirm('Annuler cette demande ?')) run(`cancel-${p.id}`, () => cancelPendingPublication(p.id), 'Demande annulée', 'annulation') }}>Annuler</button>}
                            <button type="button" className="text-xs px-2.5 py-1.5 rounded-md" style={{ ...input, color: 'var(--negative)' }} disabled={b('delete')} onClick={() => { if (confirm('Supprimer définitivement ? Le journal d’audit sera perdu.')) run(`delete-${p.id}`, () => deletePendingPublication(p.id), 'Supprimée', 'suppression') }}>Supprimer</button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Diagnostic */}
            <aside className="space-y-3">
              <div className="p-4 elev-card" style={card}>
                <div className={`${label} mb-3`} style={{ color: 'var(--text-muted)' }}>Configuration</div>
                {status ? (
                  <ul className="text-xs space-y-2" style={{ color: 'var(--text-secondary)' }}>
                    <li><Dot ok={status.encryption.configured || status.encryption.dev_derived_key} warn={status.encryption.dev_derived_key} />
                      Chiffrement {status.encryption.configured ? `actif (clé v${status.encryption.key_version})` : 'clé DEV dérivée — à configurer'}</li>
                    <li><Dot ok={status.sheet.configured} />Planning Google {status.sheet.configured ? (status.sheet.tab === '(premier onglet)' ? '· tous les onglets' : `· onglet ${status.sheet.tab}`) : 'non configuré'}</li>
                    {status.sheet.configured && <li className="pl-4" style={{ color: 'var(--text-muted)' }}>Événements : statuts {status.import_statuses.join(', ')} · vidéos livrées : {(status.video_import_statuses ?? ['validé']).join(', ')} · retour dans « {status.writeback_column ?? 'aucune colonne'} »</li>}
                    {status.sheet.service_account
                      ? <li className="font-mono text-[10px] break-all pl-4" style={{ color: 'var(--text-muted)' }}>{status.sheet.service_account} ({status.sheet.service_account_origin})</li>
                      : <li className="pl-4" style={{ color: 'var(--negative)' }}>Compte de service Google introuvable dans les variables Render</li>}
                    {!status.sheet.service_account && status.sheet.diagnostics && (
                      <li className="pl-4 space-y-1" style={{ color: 'var(--text-muted)' }}>
                        <div>Variables au nom évocateur vues par le backend (noms seulement) :</div>
                        {status.sheet.diagnostics.candidate_env_vars.length === 0
                          ? <div className="font-mono text-[10px]">aucune — le JSON n'est pas sur ce service Render</div>
                          : status.sheet.diagnostics.candidate_env_vars.map((v) => (
                            <div key={v.name} className="font-mono text-[10px] break-all">
                              {v.name} · {v.shape} · {v.length} car.{v.problem && <span style={{ color: 'var(--negative)' }}> · {v.problem}</span>}
                            </div>
                          ))}
                        <div>Fichiers secrets ({status.sheet.diagnostics.checked_dirs.join(', ')}) :</div>
                        {status.sheet.diagnostics.secret_files.length === 0
                          ? <div className="font-mono text-[10px]">aucun</div>
                          : status.sheet.diagnostics.secret_files.map((f) => (
                            <div key={f.path} className="font-mono text-[10px] break-all">{f.path} · {f.shape ?? f.error} · {f.size ?? '?'} o</div>
                          ))}
                        <div>Attendu dans <code>GOOGLE_SERVICE_ACCOUNT_JSON</code> : le fichier JSON d'une <b>clé de compte de service</b> (commence par {'{"type": "service_account"'}), pas un identifiant client OAuth. Console Google Cloud → IAM → Comptes de service → Clés → Créer une clé JSON, puis partager la feuille avec l'adresse <code>client_email</code>.</div>
                      </li>
                    )}
                    {!status.sheet.sheet_id_set && <li className="pl-4" style={{ color: 'var(--negative)' }}>PUBLICATION_SHEET_ID manquant</li>}
                    <li><Dot ok={status.buffer_configured} />Buffer {status.buffer_configured ? 'configuré' : 'non configuré'}</li>
                    <li><Dot ok />Publication manuelle après validation (bouton « Publier »)</li>
                    <li><Dot ok={status.notify_telegram || status.notify_emails > 0} />Notifications : {[status.notify_telegram && 'Telegram', status.notify_emails > 0 && `${status.notify_emails} e-mail(s)`].filter(Boolean).join(' + ') || 'aucune'}</li>
                    <li><Dot ok={status.base_url !== '(relatif)'} warn />Liens : {status.base_url} · validité {status.ttl_hours} h</li>
                  </ul>
                ) : <div className="text-xs" style={{ color: 'var(--text-muted)' }}>…</div>}
              </div>
              <div className="p-4 elev-card text-[11px] leading-relaxed" style={{ ...card, color: 'var(--text-muted)' }}>
                <div className={`${label} mb-2`}>Planning lu</div>
                « Suivi hebdomadaire des prestataires audiovisuels » : tous les onglets (un par semaine), en-têtes repérés automatiquement (Date, Événement, Heure, Prestation, Lieu, Précisions, Prestataire, Statut, Source / flyer). Toutes les 10 min, chaque événement <b>Confirmé</b> ou <b>Réalisé</b> devient une publication à valider, ainsi que chaque ligne <b>Validé</b> du tableau « Livraisons » (Vidéo, Prestataire, Validée le, Validation, liens Purevision / WeTransfer). Le texte proposé est composé depuis la ligne et reste modifiable par le validateur. Les liens WeTransfer / Purevision ne sont pas des fichiers directs : joignez la vidéo au moment de publier. L'état de validation est écrit dans une colonne <b>Publication</b> ajoutée à droite ; la colonne Statut du planning n'est jamais modifiée.
              </div>
            </aside>
          </div>
        </div>
      </main>

      {/* Publication (fichier joint facultatif) */}
      {publishTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setPublishTarget(null)}>
          <div className="max-w-lg w-full p-6 elev-card" style={card} onClick={(e) => e.stopPropagation()}>
            <div className={`${label} mb-1`} style={{ color: 'var(--text-muted)' }}>Publier sur Buffer</div>
            <h2 className="font-serif text-xl italic mb-3">{publishTarget.payload.title || '(sans titre)'}</h2>
            {(publishTarget.payload.links?.length ?? 0) > 0 && (
              <div className="text-xs mb-3 p-3 rounded-md" style={{ background: 'var(--warn-soft)', color: 'var(--warning)' }}>
                Cette publication n’a que des liens (WeTransfer / Purevision), pas de fichier direct. Téléchargez la vidéo puis joignez-la ci-dessous, sinon le post partira sans média (Instagram / TikTok seront ignorés).
                <div className="mt-1 space-y-0.5">
                  {publishTarget.payload.links!.map((u) => <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="underline block break-all" style={{ color: 'var(--accent-link)' }}>{u}</a>)}
                </div>
              </div>
            )}
            <label className="text-xs block mb-1" style={{ color: 'var(--text-secondary)' }}>Fichier à joindre (image ou vidéo, facultatif)</label>
            <input type="file" accept="image/*,video/*" className="text-xs mb-4 w-full" onChange={(e) => setPublishFile(e.target.files?.[0] ?? null)} />
            {publishFile && <div className="text-[11px] mb-3" style={{ color: 'var(--text-muted)' }}>{publishFile.name} · {(publishFile.size / 1048576).toFixed(1)} Mo</div>}
            <div className="flex gap-2">
              <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={busy === `publish-${publishTarget.id}`}
                onClick={() => { const t = publishTarget; setPublishTarget(null); run(`publish-${t.id}`, () => publishPendingPublication(t.id, publishFile ?? undefined), 'Publication envoyée', 'publication') }}>
                {publishFile ? '📤 Publier avec le fichier' : '📤 Publier sans média'}
              </button>
              <button type="button" className="text-sm underline" style={{ color: 'var(--text-muted)' }} onClick={() => setPublishTarget(null)}>Annuler</button>
            </div>
          </div>
        </div>
      )}

      {/* Détail */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setDetail(null)}>
          <div className="max-w-2xl w-full max-h-[85vh] overflow-auto p-6 elev-card" style={card} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <div className={`${label} mb-1`} style={{ color: 'var(--text-muted)' }}>Détail · {detail.id}</div>
                <h2 className="font-serif text-2xl italic">{detail.payload.title || '(sans titre)'}</h2>
              </div>
              <Badge status={detail.status} />
            </div>
            <p className="text-sm whitespace-pre-wrap mb-3" style={{ color: 'var(--text-secondary)' }}>{detail.payload.text}</p>
            {detail.payload.original_text && (
              <details className="text-xs mb-3"><summary style={{ color: 'var(--text-muted)' }}>Texte d’origine (modifié par {detail.payload.edited_by})</summary>
                <p className="whitespace-pre-wrap mt-1" style={{ color: 'var(--text-muted)' }}>{detail.payload.original_text}</p></details>
            )}
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
              <dt style={{ color: 'var(--text-muted)' }}>Demandeur</dt><dd>{detail.payload.requester || '—'} {detail.payload.requester_email && `· ${detail.payload.requester_email}`}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Lieu</dt><dd>{detail.payload.location || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Prestation</dt><dd>{[detail.payload.service, detail.payload.provider].filter(Boolean).join(' · ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Réseaux</dt><dd>{detail.payload.networks.join(', ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Date souhaitée</dt><dd>{detail.payload.scheduled_for || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Campagne</dt><dd>{detail.payload.campaign_name || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Médias</dt><dd className="break-all">{detail.payload.media_urls.join(' · ') || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Liens</dt><dd className="break-all">{(detail.payload.links ?? []).length ? detail.payload.links!.map((u) => <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="underline block" style={{ color: 'var(--accent-link)' }}>{u}</a>) : '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Notes</dt><dd>{detail.payload.notes || '—'}</dd>
              {detail.decision && <><dt style={{ color: 'var(--text-muted)' }}>Décision</dt><dd>{detail.decision.decision === 'approve' ? 'Validée' : 'Refusée'} par {detail.decision.by} le {fmt(detail.decision.at)} {detail.decision.comment && `— « ${detail.decision.comment} »`}</dd></>}
              {detail.publish && <><dt style={{ color: 'var(--text-muted)' }}>Publication</dt><dd>{detail.publish.ok ? `OK sur ${detail.publish.platforms} réseau(x) le ${fmt(detail.publish.published_at)}` : `Échec : ${detail.publish.error}`}</dd></>}
            </dl>
            <div className={`${label} mb-2`} style={{ color: 'var(--text-muted)' }}>Journal</div>
            <ul className="text-[11px] font-mono space-y-1" style={{ color: 'var(--text-muted)' }}>
              {(detail.audit ?? []).map((a, i) => (
                <li key={i}>{fmt(a.at)} · {a.action}{a.actor && ` · ${a.actor}`}{a.detail && ` · ${a.detail}`}</li>
              ))}
            </ul>
            <div className="mt-4 text-right"><button type="button" className="text-sm underline" style={{ color: 'var(--text-muted)' }} onClick={() => setDetail(null)}>Fermer</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
