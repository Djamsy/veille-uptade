'use client'

import type { CSSProperties, ReactNode } from 'react'
import { PUB_STATUS_LABEL } from '../../../lib/api'

export const label = 'font-mono text-[10px] uppercase tracking-[0.18em]'
export const card: CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }
export const input: CSSProperties = { background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)', color: 'var(--text)' }
export const btnSecondary: CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-hover)', color: 'var(--text-secondary)' }
export const btnPrimary: CSSProperties = { background: 'var(--accent-press)', border: '1px solid var(--accent-press)', color: '#fafafa' }
export const btnPositive: CSSProperties = { background: 'var(--positive)', border: '1px solid var(--positive)', color: '#fff' }

export const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '—')

export function timeAgo(iso?: string | null): string {
  if (!iso) return ''
  const ms = Date.now() - new Date(iso).getTime()
  const m = Math.floor(ms / 60000)
  if (m < 1) return 'à l’instant'
  if (m < 60) return `il y a ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `il y a ${h} h`
  const d = Math.floor(h / 24)
  if (d === 1) return 'hier'
  return `il y a ${d} j`
}

export function hoursLeft(iso?: string | null): number | null {
  if (!iso) return null
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3600000))
}

const TONE: Record<string, { bg: string; color: string }> = {
  pending: { bg: 'var(--warn-soft)', color: 'var(--warning)' },
  approved: { bg: 'var(--info-soft)', color: 'var(--accent-link)' },
  published: { bg: 'var(--ok-soft)', color: 'var(--positive)' },
  rejected: { bg: 'var(--crit-soft)', color: 'var(--negative)' },
  publish_failed: { bg: 'var(--crit-soft)', color: 'var(--negative)' },
  expired: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' },
  cancelled: { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' },
}

export function Chip({ tone = 'neutral', children, title }: { tone?: string; children: ReactNode; title?: string }) {
  const t = TONE[tone] ?? { bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' }
  return (
    <span title={title} className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-sm whitespace-nowrap"
      style={{ background: t.bg, color: t.color, border: '1px solid var(--border)' }}>{children}</span>
  )
}

export function Badge({ status }: { status: string }) {
  return <Chip tone={status}>{PUB_STATUS_LABEL[status] ?? status}</Chip>
}

export function Dot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span className="inline-block w-2 h-2 rounded-full mr-2 shrink-0" style={{ background: ok ? (warn ? 'var(--caution)' : 'var(--positive)') : 'var(--negative)' }} />
}

type IconName = 'plus' | 'refresh' | 'radar' | 'dots' | 'x' | 'check' | 'upload' | 'library' | 'link' | 'edit' | 'external' | 'image' | 'video' | 'trash' | 'tag' | 'send' | 'back' | 'search' | 'warn' | 'restore'

const PATHS: Record<IconName, string> = {
  plus: 'M12 5v14M5 12h14',
  refresh: 'M21 12a9 9 0 1 1-3-6.7M21 3v6h-6',
  radar: 'M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0M4.9 4.9a10 10 0 0 0 0 14.2M19.1 4.9a10 10 0 0 1 0 14.2M8 8a5.7 5.7 0 0 0 0 8M16 8a5.7 5.7 0 0 1 0 8',
  dots: 'M5 12h.01M12 12h.01M19 12h.01',
  x: 'M6 6l12 12M18 6 6 18',
  check: 'm5 12 5 5L20 7',
  upload: 'M12 16V4m0 0 4 4m-4-4-4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  library: 'M3 5h18v14H3zM3 15l5-5 4 4 3-3 6 6M16 9h.01',
  link: 'M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7',
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z',
  external: 'M7 17 17 7M8 7h9v9',
  image: 'M3 5h18v14H3zM3 15l5-5 4 4 3-3 6 6',
  video: 'M3 6h13v12H3zM16 10l5-3v10l-5-3',
  trash: 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6',
  tag: 'M20 12 12 20l-9-9V3h8ZM7 7h.01',
  send: 'M22 2 11 13M22 2l-7 20-4-9-9-4Z',
  back: 'M19 12H5M12 19l-7-7 7-7',
  search: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-4.3-4.3',
  warn: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  restore: 'M3 12a9 9 0 1 0 3-6.7M3 3v6h6',
}

export function Icon({ name, size = 14, stroke = 2 }: { name: IconName; size?: number; stroke?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  )
}

export function IconButton({ name, title, onClick, disabled, style }: { name: IconName; title: string; onClick?: () => void; disabled?: boolean; style?: CSSProperties }) {
  return (
    <button type="button" aria-label={title} title={title} onClick={onClick} disabled={disabled}
      className="w-8 h-8 rounded-md inline-flex items-center justify-center shrink-0" style={{ ...btnSecondary, ...style }}>
      <Icon name={name} />
    </button>
  )
}
