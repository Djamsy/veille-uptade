// lib/api.ts — Client API V2 pour Veille Média Guadeloupe
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

// ============================================================
// TYPES
// ============================================================
export interface Affair {
  _id: string;
  title: string;
  description?: string;
  primary_entity?: string;
  entities: string[];
  elected?: string[];
  institutions?: string[];
  theme: string;
  gravity_score: number;
  affair_type: string;
  status: string;
  bmg: number;
  bmg_details?: BmgDetails;
  bmg_history?: Array<{ bmg: number; at: string }>;
  articles: string[];
  radio_transcriptions: string[];
  social_posts: string[];
  sources: string[];
  source_types: string[];
  item_count: number;
  created_at: string;
  last_activity: string;
  promoted_at?: string;
}

export interface BmgDetails {
  bmg: number;
  bnp_by_canal: Record<string, number>;
  niveau_alerte: string;
  total_items: number;
  active_canals: number;
  dominant_canal: string | null;
  multi_canal_bonus: boolean;
  calculated_at: string;
}

export interface Article {
  _id: string;
  title: string;
  content?: string;
  source: string;
  url?: string;
  date: string;
  scraped_at?: string;
  theme?: string;
  elected?: string[];
  institutions?: string[];
  gravity_score?: number;
  sentiment?: string;
  is_affair?: boolean;
}

export interface TimelineEvent {
  _id: string;
  affair_id: string;
  event: string;
  details: Record<string, unknown>;
  timestamp: string;
}

export interface DashboardData {
  top_affairs: Affair[];
  critical_alerts: Affair[];
  stats: SystemStats;
  timestamp: string;
}

export interface SystemStats {
  status: string;
  candidates_total: number;
  candidates_unclustered: number;
  clusters_active: number;
  affairs_active: number;
  affairs_stale: number;
}

export interface LinkedArticle {
  _id: string;
  title: string;
  source: string;
  url?: string;
  date: string;
  scraped_at?: string;
  theme?: string;
  gravity_score?: number;
  sentiment?: string;
}

export interface LinkedRadio {
  _id: string;
  radio: string;
  text: string;
  captured_at?: string;
  summary?: string;
}

export interface LinkedSocial {
  _id: string;
  platform: string;
  text: string;
  author?: string;
  url?: string;
  created_at?: string;
}

export interface AffairDetailResponse {
  affair: Affair;
  timeline: TimelineEvent[];
  bmg_live: BmgDetails;
  linked_articles: LinkedArticle[];
  linked_radio: LinkedRadio[];
  linked_social: LinkedSocial[];
}

export interface ReconciliationStats {
  total: number;
  reconciled: number;
  no_match: number;
  skipped: number;
  errors: number;
}

export interface RadioCard {
  id: string;
  title: string;
  subtitle: string;
  summary: string;
  fullSummary?: string;
  fullText?: string;
  isTruncated: boolean;
  summarySource: 'gpt' | 'transcription';
  audioUrl?: string | null;
  type: string;
  source?: string;
  capturedAt?: string;
  timezone?: string;
  meta?: {
    transcriptionMethod?: string;
    analysisMethod?: string;
  };
}

export interface RadioCardsResponse {
  success: boolean;
  date: string;
  cards: RadioCard[];
  pagination?: {
    total: number;
    offset: number;
    returned: number;
    hasMore: boolean;
  };
}

// ============================================================
// API CALLS
// ============================================================

// --- Dashboard ---
export const fetchDashboard = () =>
  apiFetch<DashboardData>('/api/affairs/dashboard');

// --- Affaires ---
export const fetchAffairs = (status = 'active', limit = 30, sortBy = 'bmg') =>
  apiFetch<{ affairs: Affair[]; total: number }>(
    `/api/affairs/list?status=${status}&limit=${limit}&sort_by=${sortBy}`
  );

export const fetchAffairDetail = (id: string) =>
  apiFetch<AffairDetailResponse>(
    `/api/affairs/detail/${id}`
  );

export const recalculateBmg = (id: string) =>
  apiFetch<{ success: boolean; bmg: BmgDetails }>(
    `/api/affairs/recalculate-bmg/${id}`, { method: 'POST' }
  );

export const runFullCycle = () =>
  apiFetch<Record<string, unknown>>('/api/affairs/cycle/run', { method: 'POST' });

// --- Articles ---
export const fetchArticles = (limit = 30, skip = 0) =>
  apiFetch<{ articles: Article[]; total: number }>(
    `/api/articles?limit=${limit}&skip=${skip}`
  );

// --- Réconciliation ---
export const fetchReconciliationHealth = () =>
  apiFetch<Record<string, unknown>>('/api/reconciliation/health');

export const fetchArticleIndex = () =>
  apiFetch<Record<string, unknown>>('/api/reconciliation/index/status');

export const runReconciliation = (days = 3, dryRun = false) =>
  apiFetch<{ success: boolean; stats: ReconciliationStats }>(
    `/api/reconciliation/transcriptions/batch?days=${days}&dry_run=${dryRun}`,
    { method: 'POST' }
  );

// --- Radio ---
export const fetchRadioCardsToday = (limit = 20) =>
  apiFetch<RadioCardsResponse>(`/api/radio/cards/today?limit=${limit}`);

export const fetchRadioCards = (date?: string, limit = 50, offset = 0) => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (date) params.set('date', date);
  return apiFetch<RadioCardsResponse>(`/api/radio/cards?${params}`);
};

export const fetchRadioCardById = (id: string) =>
  apiFetch<{ success: boolean; card: RadioCard; raw: Record<string, unknown> }>(
    `/api/radio/cards/${id}`
  );

export const captureRadioNow = (section = '', duration = 20) =>
  apiFetch<{ success: boolean; card: RadioCard; used_key: string }>(
    `/api/radio/capture?section=${encodeURIComponent(section)}&duration=${duration}`,
    { method: 'POST' }
  );

export const refreshRadioSnapshot = (date?: string) =>
  apiFetch<{ success: boolean; count: number; cards: RadioCard[] }>(
    '/api/radio/cards/refresh-snapshot',
    { method: 'POST', body: JSON.stringify(date ? { date } : {}) }
  );

export const fetchRadioDebugStreams = () =>
  apiFetch<{ success: boolean; streams: Array<{ key: string; name: string; enabled: boolean }> }>(
    '/api/radio/debug/streams'
  );

// --- Santé système ---
export const fetchHealth = () => apiFetch<Record<string, unknown>>('/health');

export const fetchAffairSystemHealth = () =>
  apiFetch<SystemStats>('/api/affairs/health');
