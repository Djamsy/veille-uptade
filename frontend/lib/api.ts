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
  priority?: 'hot' | 'watch' | 'minor';
  sentiment?: string;
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

export interface CoverageStats {
  total_articles_7d: number;
  enriched_articles_7d: number;
  affiliated_articles_7d: number;
  total_transcriptions_7d: number;
  processed_transcriptions_7d: number;
  affiliation_rate: number;
  enrichment_rate: number;
  radio_rate: number;
}

export interface DailyActivity {
  date: string;
  label: string;
  articles: number;
  events: number;
}

export interface TopEntity {
  name: string;
  count: number;
}

export interface TopSource {
  name: string;
  count: number;
}

export interface OrphanArticle {
  _id: string;
  title: string;
  source: string;
  theme: string;
  gravity_score: number;
  scraped_at: string;
}

export interface TrendData {
  articles_this_week: number;
  articles_last_week: number;
  articles_trend_pct: number;
  affairs_created_this_week: number;
  affairs_created_last_week: number;
}

export interface EnrichedDashboardData {
  top_affairs: Affair[];
  critical_alerts: Affair[];
  stats: SystemStats;
  coverage: CoverageStats;
  themes_distribution: Record<string, number>;
  top_entities: TopEntity[];
  daily_activity: DailyActivity[];
  orphan_articles: OrphanArticle[];
  recent_timeline: TimelineEvent[];
  top_sources: TopSource[];
  gravity_distribution?: { low: number; medium: number; high: number; critical: number };
  avg_gravity?: number;
  sentiment_distribution?: Record<string, number>;
  priority_counts?: Record<string, number>;
  avg_bmg?: number;
  trends?: TrendData;
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
  topic_title?: string;
  topic_summary?: string;
  gravity?: number;
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

export const fetchEnrichedDashboard = () =>
  apiFetch<EnrichedDashboardData>('/api/affairs/dashboard/enriched');

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

export const runScrapeNow = () =>
  apiFetch<Record<string, unknown>>('/api/scheduler/scrape-now', { method: 'POST' });

export const runFullPipeline = () =>
  apiFetch<Record<string, unknown>>('/api/scheduler/run-pipeline', { method: 'POST' });

export const runBulkEnrich = (batchSize = 100, days = 90) =>
  apiFetch<{ success: boolean; enriched: number; embeddings: number; remaining: number; message: string }>(
    `/api/scheduler/bulk-enrich?batch_size=${batchSize}&days=${days}`, { method: 'POST' }
  );

export const runReaffiliate = () =>
  apiFetch<{ success: boolean; reaffiliated: number; message: string }>(
    '/api/affairs/cycle/reaffiliate', { method: 'POST' }
  );

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

export interface StreamHealthResult {
  key: string;
  name: string;
  section: string;
  type: string;
  url: string;
  enabled: boolean;
  status: 'ok' | 'warning' | 'error' | 'disabled' | 'unknown';
  latency_ms: number | null;
  content_type: string | null;
  http_status?: number;
  bytes_received?: number;
  error: string | null;
  checked_at: string;
}

export interface StreamHealthResponse {
  success: boolean;
  summary: {
    total: number;
    ok: number;
    warning: number;
    error: number;
    disabled: number;
    health_score: number;
  };
  streams: StreamHealthResult[];
  checked_at: string;
}

export const fetchRadioHealthCheck = () =>
  apiFetch<StreamHealthResponse>('/api/radio/health-check');

export const fetchRadioHealthCheckSingle = (key: string) =>
  apiFetch<{ success: boolean; stream: StreamHealthResult }>(
    `/api/radio/health-check/${key}`, { method: 'POST' }
  );

export const fetchRadioHealthCheckLast = () =>
  apiFetch<{ success: boolean; streams: StreamHealthResult[]; checked_at?: string; ok?: number; errors?: number }>(
    '/api/radio/health-check/last'
  );

// --- Réseaux sociaux (Apify) ---
export interface SocialPost {
  _id: string;
  platform: 'facebook' | 'instagram' | 'twitter';
  author: string;
  text: string;
  url: string;
  posted_at: string;
  likes: number;
  comments?: number;
  shares?: number;
  retweets?: number;
  scraped_at: string;
}

export interface SocialStats {
  stats: Record<string, {
    total: number;
    last_24h: number;
    last_7d: number;
    last_scraped: string | null;
  }>;
  timestamp: string;
}

export const fetchSocialStats = () =>
  apiFetch<SocialStats>('/api/social/stats');

export const fetchSocialPosts = (platform?: string, limit = 50) =>
  apiFetch<{ posts: SocialPost[]; count: number }>(
    `/api/social/posts?limit=${limit}${platform ? `&platform=${platform}` : ''}`
  );

export const fetchSocialScrapeAll = () =>
  apiFetch<Record<string, unknown>>('/api/social/scrape', { method: 'POST' });

export const fetchSocialScrapeSingle = (platform: string) =>
  apiFetch<Record<string, unknown>>(`/api/social/scrape/${platform}`, { method: 'POST' });

export const fetchSocialConfig = () =>
  apiFetch<Record<string, unknown>>('/api/social/config');

// --- Santé système ---
export const fetchHealth = () => apiFetch<Record<string, unknown>>('/health');

export const fetchAffairSystemHealth = () =>
  apiFetch<SystemStats>('/api/affairs/health');
