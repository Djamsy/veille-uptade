'use client'

import { useState } from 'react'
import type { PendingPublication } from '../../../lib/api'
import { displayUrl, isVideoUrl } from '../../../lib/media'
import { Chip, Icon, IconButton, btnPositive, btnPrimary, btnSecondary, card, hoursLeft, label, timeAgo } from './common'

export interface FlowActions {
  edit: (p: PendingPublication) => void
  resend: (p: PendingPublication) => void
  newLink: (p: PendingPublication) => void
  revoke: (p: PendingPublication) => void
  cancel: (p: PendingPublication) => void
  remove: (p: PendingPublication) => void
  publish: (p: PendingPublication) => void
  detail: (p: PendingPublication) => void
}

const COL1 = new Set(['pending', 'expired'])
const COL2 = new Set(['approved', 'publish_failed'])
const COL3 = new Set(['published'])

function Thumb({ p, size = 72 }: { p: PendingPublication; size?: number }) {
  const [broken, setBroken] = useState(false)
  const urls = p.payload?.media_urls ?? []
  const first = urls[0]
  const n = urls.length
  const box = { width: size, height: size, borderRadius: 6, flexShrink: 0, background: 'var(--bg-elevated)', border: '1px solid var(--border)', overflow: 'hidden', position: 'relative' as const }
  if (first && !broken) {
    return (
      <div style={box}>
        {isVideoUrl(first)
          ? <video src={displayUrl(first)} className="w-full h-full object-cover" muted preload="metadata" />
          // eslint-disable-next-line @next/next/no-img-element
          : <img src={displayUrl(first, 300)} alt="" className="w-full h-full object-cover" loading="lazy" onError={() => setBroken(true)} />}
        {n > 1 && <span className="absolute bottom-1 right-1 text-[10px] font-semibold px-1.5 rounded" style={{ background: 'rgba(0,0,0,0.65)', color: '#fff' }}>+{n - 1}</span>}
      </div>
    )
  }
  const links = p.payload?.links?.length ?? 0
  return (
    <div style={{ ...box, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 4, color: 'var(--text-muted)' }}>
      <Icon name={p.payload?.kind === 'video' || links ? 'video' : 'image'} size={18} stroke={1.6} />
      <span className="text-[9px]">{links ? `${links} lien${links > 1 ? 's' : ''}` : 'sans média'}</span>
    </div>
  )
}

function Origin({ p }: { p: PendingPublication }) {
  if (p.source === 'sheet') return <>{p.payload?.kind === 'video' ? 'Livraison vidéo' : 'Planning'}{p.sheet_tab ? ` ${p.sheet_tab.split(' - ')[0]}` : ''}{p.sheet_row ? ` · ligne ${p.sheet_row}` : ''}</>
  return <>Saisie manuelle</>
}

function Card({ p, busy, a }: { p: PendingPublication; busy: string; a: FlowActions }) {
  const [menu, setMenu] = useState(false)
  const b = (k: string) => busy === `${k}-${p.id}`
  const st = p.status
  const pay = p.payload ?? ({} as PendingPublication['payload'])
  const noMedia = (pay.media_urls?.length ?? 0) === 0
  const linkOk = p.token.active && !p.token.expired
  const hl = hoursLeft(p.token.expires_at)
  const draft = st === 'pending' && p.source === 'sheet' && noMedia

  let primary: { label: string; style: React.CSSProperties; onClick: () => void; busyKey?: string; href?: string } | null = null
  if (COL1.has(st)) {
    if (draft) primary = { label: 'Compléter', style: btnPrimary, onClick: () => a.edit(p) }
    else if (!linkOk) primary = { label: 'Renvoyer le lien', style: btnSecondary, onClick: () => a.resend(p), busyKey: 'resend' }
    else primary = { label: 'Modifier', style: btnSecondary, onClick: () => a.edit(p) }
  } else if (COL2.has(st)) {
    primary = { label: st === 'publish_failed' ? 'Réessayer' : 'Publier', style: btnPositive, onClick: () => a.publish(p), busyKey: 'publish' }
  } else if (COL3.has(st)) {
    const url = p.publish?.url || p.seen?.best?.url
    primary = url ? { label: 'Voir le post', style: btnSecondary, onClick: () => window.open(url, '_blank', 'noopener'), href: url } : { label: 'Détail', style: btnSecondary, onClick: () => a.detail(p) }
  } else {
    primary = { label: 'Détail', style: btnSecondary, onClick: () => a.detail(p) }
  }

  let statusLine: React.ReactNode = null
  if (st === 'pending') {
    statusLine = draft
      ? <Chip tone="expired">Brouillon · ajoutez des visuels puis envoyez le lien</Chip>
      : linkOk
        ? <Chip tone="pending" title={p.token.expires_at ?? ''}>Lien envoyé · expire dans {hl} h</Chip>
        : <Chip tone="rejected">Lien {p.token.revoked ? 'révoqué' : 'expiré'}, pas de décision</Chip>
  } else if (st === 'expired') statusLine = <Chip tone="rejected">Lien expiré sans décision</Chip>
  else if (st === 'approved') statusLine = (
    <>
      <Chip tone="approved">Validée par {p.decision?.by ?? '—'} · {timeAgo(p.decision?.at)}</Chip>
      {p.seen && !p.seen.matched && <Chip tone="pending">Pas encore vue sur les réseaux</Chip>}
    </>
  )
  else if (st === 'publish_failed') statusLine = <Chip tone="rejected" title={p.publish?.error ?? ''}>Échec de publication : {p.publish?.error?.slice(0, 60) ?? 'inconnu'}</Chip>
  else if (st === 'published') statusLine = p.publish?.via === 'detected_on_social'
    ? <Chip tone="published">Constatée sur {p.publish.platform} · {p.publish.how}</Chip>
    : <Chip tone="published">Publiée via Buffer · {p.publish?.platforms ?? 0} réseau(x) · {timeAgo(p.publish?.published_at)}</Chip>
  else if (st === 'rejected') statusLine = <Chip tone="rejected">Refusée par {p.decision?.by ?? '—'}{p.decision?.comment ? ` · « ${p.decision.comment.slice(0, 50)} »` : ''}</Chip>
  else if (st === 'cancelled') statusLine = <Chip tone="cancelled">Annulée</Chip>

  return (
    <article className="flex flex-col gap-2.5 p-3 elev-card" style={{ ...card, borderStyle: draft ? 'dashed' : 'solid' }}>
      <div className="flex gap-3">
        <Thumb p={p} />
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}><Origin p={p} /> · {timeAgo(p.created_at)}</span>
          <button type="button" onClick={() => a.detail(p)} className="text-left">
            <strong className="text-sm leading-snug line-clamp-2 hover:underline">{pay.title || pay.text?.slice(0, 80) || p.error || '(sans titre)'}</strong>
          </button>
          <span className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
            {[pay.scheduled_for, pay.location].filter(Boolean).join(' · ') || pay.text?.replace(/\s+/g, ' ').slice(0, 90)}
          </span>
          {st === 'approved' && p.decision?.comment && <span className="text-xs italic truncate" style={{ color: 'var(--text-muted)' }}>« {p.decision.comment} »</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex gap-1.5 flex-wrap min-w-0">{statusLine}</div>
        <div className="ml-auto flex items-center gap-1.5 relative">
          {primary && (
            <button type="button" onClick={primary.onClick} disabled={primary.busyKey ? b(primary.busyKey) : false}
              className="text-xs font-semibold px-3 py-2 rounded-md whitespace-nowrap" style={primary.style}>
              {primary.busyKey && b(primary.busyKey) ? '…' : primary.label}
            </button>
          )}
          <IconButton name="dots" title="Autres actions" onClick={() => setMenu((v) => !v)} />
          {menu && (
            <div className="absolute right-0 top-9 z-30 min-w-[200px] py-1 rounded-md" style={{ ...card, boxShadow: 'var(--shadow-elevated)' }} onMouseLeave={() => setMenu(false)}>
              {[
                { l: 'Détail et historique', f: () => a.detail(p), show: true },
                { l: 'Modifier', f: () => a.edit(p), show: COL1.has(st) && !draft },
                { l: 'Nouveau lien (copier)', f: () => a.newLink(p), show: COL1.has(st) },
                { l: 'Renvoyer le lien aux validateurs', f: () => a.resend(p), show: COL1.has(st) },
                { l: 'Révoquer le lien', f: () => a.revoke(p), show: st === 'pending' && p.token.active },
                { l: 'Publier', f: () => a.publish(p), show: COL2.has(st) },
                { l: 'Annuler la demande', f: () => a.cancel(p), show: COL1.has(st) || COL2.has(st) },
                { l: 'Supprimer définitivement', f: () => a.remove(p), show: true, danger: true },
              ].filter((i) => i.show).map((i) => (
                <button key={i.l} type="button" onClick={() => { setMenu(false); i.f() }}
                  className="w-full text-left text-xs px-3 py-2 hover:underline" style={{ color: i.danger ? 'var(--negative)' : 'var(--text)' }}>{i.l}</button>
              ))}
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

function Column({ title, tone, items, busy, a, empty, counter }: { title: string; tone: string; items: PendingPublication[]; busy: string; a: FlowActions; empty: string; counter?: string }) {
  return (
    <section className="flex flex-col gap-3 min-w-0" aria-label={title}>
      <div className="flex items-center gap-2 px-1">
        <span className="w-2 h-2 rounded-full" style={{ background: tone }} aria-hidden="true" />
        <h2 className="m-0 text-xs font-semibold tracking-[0.14em] uppercase" style={{ color: 'var(--text-secondary)' }}>{title}</h2>
        <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>{counter ?? items.length}</span>
      </div>
      {items.length === 0
        ? <div className="p-5 text-center text-xs rounded-lg" style={{ border: '1px dashed var(--border-strong)', color: 'var(--text-muted)' }}>{empty}</div>
        : items.map((p) => <Card key={p.id} p={p} busy={busy} a={a} />)}
    </section>
  )
}

export function FlowBoard({ pubs, busy, actions }: { pubs: PendingPublication[]; busy: string; actions: FlowActions }) {
  const [showClosed, setShowClosed] = useState(false)
  const col1 = pubs.filter((p) => COL1.has(p.status))
  const col2 = pubs.filter((p) => COL2.has(p.status))
  const col3 = pubs.filter((p) => COL3.has(p.status))
  const closed = pubs.filter((p) => p.status === 'rejected' || p.status === 'cancelled')
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        <Column title="À valider" tone="var(--caution)" items={col1} busy={busy} a={actions} empty="Rien à valider. Le planning est lu toutes les 10 min ; vous pouvez aussi créer une publication." />
        <Column title="Validées · à publier" tone="var(--accent-link)" items={col2} busy={busy} a={actions} empty="Aucune publication validée en attente de mise en ligne." />
        <Column title="Publiées" tone="var(--positive)" items={col3.slice(0, 20)} busy={busy} a={actions} empty="Aucune publication constatée ou envoyée récemment." counter={col3.length > 20 ? `20 / ${col3.length}` : undefined} />
      </div>
      {closed.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs px-1" style={{ color: 'var(--text-muted)' }}>
            <span>Refusées et annulées : {closed.length}</span>
            <button type="button" className="ml-auto underline" onClick={() => setShowClosed((v) => !v)}>{showClosed ? 'Masquer' : 'Afficher'}</button>
          </div>
          {showClosed && (
            <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
              {closed.map((p) => <Card key={p.id} p={p} busy={busy} a={actions} />)}
            </div>
          )}
        </div>
      )}
      <p className={`${label} px-1`} style={{ color: 'var(--text-muted)' }}>Les validateurs reçoivent un lien personnel par Telegram · vous publiez ensuite depuis la colonne « Validées »</p>
    </div>
  )
}
