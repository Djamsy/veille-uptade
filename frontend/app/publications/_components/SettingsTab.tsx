'use client'

import type { fetchPubValidationStatus } from '../../../lib/api'
import { Dot, card, fmt, label } from './common'

export type PubStatus = Awaited<ReturnType<typeof fetchPubValidationStatus>>

/** Vrai si une brique indispensable manque : l'écran Flux affiche alors une alerte. */
export function statusProblems(s: PubStatus | null): string[] {
  if (!s) return []
  const p: string[] = []
  if (!s.encryption.configured && !s.encryption.dev_derived_key) p.push('Chiffrement non configuré')
  if (!s.cloudinary?.configured) p.push('Hébergement des médias (Cloudinary) non configuré — l’ajout de photos échouera')
  if (!s.sheet.configured) p.push('Planning Google non configuré')
  if (!s.buffer_configured) p.push('Buffer non configuré — la publication depuis l’espace est impossible')
  if (!s.notify_telegram && s.notify_emails === 0) p.push('Aucun canal de notification : les validateurs ne recevront pas les liens')
  return p
}

function Section({ title, ok, summary, children, open }: { title: string; ok: boolean; summary?: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="p-3.5 elev-card" style={card}>
      <summary className="flex items-center gap-2 text-sm font-semibold cursor-pointer list-none">
        <Dot ok={ok} warn={!ok} />{title}
        {summary && <span className="ml-auto text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>{summary}</span>}
      </summary>
      <div className="mt-3 flex flex-col gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>{children}</div>
    </details>
  )
}

export function SettingsTab({ status }: { status: PubStatus | null }) {
  if (!status) return <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Chargement…</div>
  const problems = statusProblems(status)
  const sc = status.social_check
  return (
    <div className="flex flex-col gap-5 max-w-3xl">
      <div>
        <h1 className="m-0 font-serif italic font-medium text-3xl tracking-tight">Réglages</h1>
        <p className="m-0 mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>État des briques et paramètres. Les valeurs se changent dans les variables du serveur (Render).</p>
      </div>

      <Section title="État du système" ok={problems.length === 0} summary={problems.length ? `${problems.length} point(s) à corriger` : 'tout fonctionne'} open>
        <div className="flex items-center"><Dot ok={status.encryption.configured || status.encryption.dev_derived_key} warn={status.encryption.dev_derived_key} />Chiffrement {status.encryption.configured ? `actif · clé v${status.encryption.key_version}` : 'clé de développement — à configurer'}</div>
        <div className="flex items-center"><Dot ok={status.sheet.configured} />Planning Google {status.sheet.configured ? `· ${status.sheet.tab === '(premier onglet)' ? 'tous les onglets' : status.sheet.tab}` : 'non configuré'}</div>
        {status.sheet.service_account && <div className="font-mono text-[10px] pl-4 break-all" style={{ color: 'var(--text-muted)' }}>{status.sheet.service_account} ({status.sheet.service_account_origin})</div>}
        <div className="flex items-center"><Dot ok={!!status.cloudinary?.configured} />Hébergement des médias (Cloudinary) {status.cloudinary?.configured ? 'configuré' : 'NON configuré'}</div>
        {status.cloudinary?.last_error && <div className="font-mono text-[10px] pl-4 break-all" style={{ color: 'var(--negative)' }}>dernier échec {status.cloudinary.last_error_at ? fmt(status.cloudinary.last_error_at) : ''} : {status.cloudinary.last_error}</div>}
        <div className="flex items-center"><Dot ok={status.buffer_configured} />Buffer {status.buffer_configured ? 'configuré' : 'non configuré'}</div>
        <div className="flex items-center"><Dot ok={!!sc && !sc.error} warn={!sc?.last} />Rapprochement réseaux : {sc?.error ? sc.error : sc?.last ? `dernier passage ${fmt(sc.last.last_run)} · ${sc.last.posts_examined} posts · ${sc.last.newly_detected} constatée(s)` : 'jamais lancé'}</div>
        <div className="flex items-center"><Dot ok={status.notify_telegram || status.notify_emails > 0} />Notifications : {[status.notify_telegram && 'Telegram', status.notify_emails > 0 && `${status.notify_emails} e-mail(s)`].filter(Boolean).join(' + ') || 'aucune'}</div>
        {status.sheet.diagnostics && !status.sheet.service_account && (
          <div className="pl-4 mt-1 flex flex-col gap-1" style={{ color: 'var(--text-muted)' }}>
            <div>Variables au nom évocateur vues par le serveur (noms seulement) :</div>
            {status.sheet.diagnostics.candidate_env_vars.length === 0 ? <div className="font-mono text-[10px]">aucune</div>
              : status.sheet.diagnostics.candidate_env_vars.map((v) => <div key={v.name} className="font-mono text-[10px] break-all">{v.name} · {v.shape} · {v.length} car.{v.problem && <span style={{ color: 'var(--negative)' }}> · {v.problem}</span>}</div>)}
          </div>
        )}
      </Section>

      <Section title="Validateurs et liens" ok={status.notify_telegram || status.notify_emails > 0}>
        <div>Liens personnels envoyés sur Telegram{status.notify_emails ? ` et par e-mail (${status.notify_emails} destinataire(s))` : ''} · validité {status.ttl_hours} h · usage unique, révocable.</div>
        <div>Adresse des liens : <span className="font-mono">{status.base_url}</span>/valider/…</div>
        <div>Publication manuelle après validation (bouton « Publier » dans le flux).</div>
      </Section>

      <Section title="Planning Google" ok={status.sheet.configured}>
        <div>Événements importés quand leur statut est : {status.import_statuses.join(', ')}.</div>
        <div>Vidéos du tableau « Livraisons » importées quand Validation vaut : {(status.video_import_statuses ?? ['validé']).join(', ')}.</div>
        <div>Retour d’état dans la colonne « {status.writeback_column ?? '—'} » ; la colonne Statut du planning n’est jamais modifiée. Lecture toutes les 10 min.</div>
      </Section>

      <Section title="Rapprochement avec les réseaux" ok={!!sc && !sc.error}>
        {sc && !sc.error ? (
          <>
            <div>Comptes suivis : {sc.accounts.join(', ')}</div>
            <div>Seuil {Math.round(sc.threshold * 100)} % · fenêtre {sc.days} jours · 3 passages par jour après le scraping des réseaux.</div>
            <div>Une publication validée retrouvée sur un compte du Département passe automatiquement en « Publiée, constatée sur … ». Un post ne peut être attribué qu’à une seule publication.</div>
          </>
        ) : <div>{sc?.error ?? 'Indisponible'}</div>}
      </Section>
    </div>
  )
}
