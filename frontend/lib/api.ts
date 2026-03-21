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

function authHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

function adminFetch<T>(path: string, options?: RequestInit): Promise<T> {
  return apiFetch<T>(path, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  });
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
  adminFetch<DashboardData>('/api/affairs/dashboard');

export const fetchEnrichedDashboard = () =>
  adminFetch<EnrichedDashboardData>('/api/affairs/dashboard/enriched');

// --- Affaires ---
export const fetchAffairs = (status = 'active', limit = 30, sortBy = 'bmg') =>
  adminFetch<{ affairs: Affair[]; total: number }>(
    `/api/affairs/list?status=${status}&limit=${limit}&sort_by=${sortBy}`
  );

export const fetchAffairDetail = (id: string) =>
  adminFetch<AffairDetailResponse>(
    `/api/affairs/detail/${id}`
  );

export const recalculateBmg = (id: string) =>
  adminFetch<{ success: boolean; bmg: BmgDetails }>(
    `/api/affairs/recalculate-bmg/${id}`, { method: 'POST' }
  );

export interface AffairContext {
  contexte: string;
  enjeux: string[];
  historique: string;
  impact_potentiel: string;
  bruit_score: number;
  sentiment_ia: string;
  mots_cles_contexte: string[];
  generated_at?: string;
}

export const generateAffairContext = (id: string) =>
  adminFetch<{ affair_id: string; ai_context: AffairContext; sentiment_updated: boolean; gravity_adjusted: boolean }>(
    `/api/affairs/generate-context/${id}`, { method: 'POST' }
  );

export const fetchAffairContext = (id: string) =>
  adminFetch<AffairContext>(`/api/affairs/context/${id}`);

export const runFullCycle = () =>
  adminFetch<Record<string, unknown>>('/api/affairs/cycle/run', { method: 'POST' });

export const runScrapeNow = () =>
  adminFetch<Record<string, unknown>>('/api/scheduler/scrape-now', { method: 'POST' });

export const runFullPipeline = () =>
  adminFetch<Record<string, unknown>>('/api/scheduler/run-pipeline', { method: 'POST' });

export const runBulkEnrich = (batchSize = 100, days = 90) =>
  adminFetch<{ success: boolean; enriched: number; embeddings: number; remaining: number; message: string }>(
    `/api/scheduler/bulk-enrich?batch_size=${batchSize}&days=${days}`, { method: 'POST' }
  );

export const runReaffiliate = () =>
  adminFetch<{ success: boolean; reaffiliated: number; message: string }>(
    '/api/affairs/cycle/reaffiliate', { method: 'POST' }
  );

// --- Articles ---
export const fetchArticles = (limit = 30, skip = 0) =>
  apiFetch<{ articles: Article[]; total: number }>(
    `/api/articles?limit=${limit}&skip=${skip}`
  );

// --- Réconciliation ---
export const fetchReconciliationHealth = () =>
  adminFetch<Record<string, unknown>>('/api/reconciliation/health');

export const fetchArticleIndex = () =>
  adminFetch<Record<string, unknown>>('/api/reconciliation/index/status');

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
  adminFetch<StreamHealthResponse>('/api/radio/health-check');

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
  replies?: number;
  scraped_at: string;
  image_url?: string;
  media_type?: string;
  ai_enriched?: boolean;
  ai_relevant?: boolean;
  ai_summary?: string;
  theme?: string;
  gravity_score?: number;
  elected?: string[];
  institutions?: string[];
  entities?: string[];
  keywords_found?: string[];
  first_seen?: string;
}

export interface SocialSentiment {
  period: string;
  global: {
    total_posts: number;
    total_engagement: number;
    total_likes: number;
    total_comments: number;
    total_shares: number;
    avg_gravity: number;
    enriched: number;
    relevant: number;
  };
  by_platform: Record<string, { count: number; likes: number; comments: number; avg_gravity: number }>;
  top_themes: Array<{ theme: string; count: number }>;
  top_elected: Array<{ name: string; count: number }>;
  top_posts: SocialPost[];
  timestamp: string;
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
  adminFetch<SocialStats>('/api/social/stats');

export const fetchSocialPosts = (platform?: string, limit = 50) =>
  apiFetch<{ posts: SocialPost[]; count: number }>(
    `/api/social/posts?limit=${limit}${platform ? `&platform=${platform}` : ''}`
  );

export const fetchSocialScrapeAll = () =>
  adminFetch<Record<string, unknown>>('/api/social/scrape', { method: 'POST' });

export const fetchSocialScrapeSingle = (platform: string) =>
  apiFetch<Record<string, unknown>>(`/api/social/scrape/${platform}`, { method: 'POST' });

export const fetchSocialConfig = () =>
  adminFetch<Record<string, unknown>>('/api/social/config');

export const fetchSocialSentiment = () =>
  adminFetch<SocialSentiment>('/api/social/sentiment');

export const fetchSocialPostDetail = (id: string) =>
  apiFetch<{ post: SocialPost & { raw?: Record<string, unknown> } }>(`/api/social/posts/${id}`);

// --- Elections & Carte ---
export const fetchAffairsByCommune = () =>
  adminFetch<{ communes: Record<string, { count: number; maxGravity: number; affairs: Array<{ _id: string; title: string; gravity_score: number; sentiment: string; theme: string }> }>; total_affairs: number }>(
    '/api/affairs/by-commune'
  );

export const fetchElectionsAffairs = () =>
  adminFetch<{ affairs: Affair[]; total: number }>('/api/affairs/elections');

// --- Compétences institutionnelles ---
export interface CompetenceGroup {
  color: string;
  count: number;
  max_gravity: number;
  affairs: Array<Affair & { competences?: string[]; communes?: string[] }>;
}

export interface InstitutionResponse {
  institution: string;
  groups: Record<string, CompetenceGroup>;
  total_matched: number;
  total_unmatched: number;
  unmatched: Array<Affair & { communes?: string[] }>;
}

export const fetchAffairsByInstitution = (institution: 'departement' | 'region') =>
  adminFetch<InstitutionResponse>(`/api/affairs/by-institution?institution=${institution}`);

// --- Analyse prédictive IA ---
export interface PredictiveItem {
  titre: string;
  description: string;
  confiance: number;
}

export interface PredictiveAnalysis {
  tendances: PredictiveItem[];
  anticipations: PredictiveItem[];
  recommandations: PredictiveItem[];
  risques: PredictiveItem[];
  synthese: string;
}

export const fetchPredictiveAnalysis = () =>
  adminFetch<{ success: boolean; analysis: PredictiveAnalysis; affairs_analyzed: number }>(
    '/api/affairs/analytics/predictive'
  );

// --- Santé système ---
export const fetchHealth = () => apiFetch<Record<string, unknown>>('/health');

export const fetchAffairSystemHealth = () =>
  adminFetch<SystemStats>('/api/affairs/health');

// ============================================================
// ADMIN — Pilotage manuel des affaires
// ============================================================

// --- Auth ---
export const fetchCurrentUser = () =>
  adminFetch<{ success: boolean; user: { id: string; email: string; name: string; role: string } }>(
    '/api/auth/me'
  );

// --- Users ---
export const fetchUsers = () =>
  adminFetch<{ users: Array<{ _id: string; email: string; name: string; role: string; created_at: string }>; total: number }>(
    '/api/admin/users'
  );

export const updateUserRole = (userId: string, role: string) =>
  adminFetch<{ success: boolean }>('/api/admin/users/' + userId + '/role', {
    method: 'PUT',
    body: JSON.stringify({ role }),
  });

// --- Affaires admin ---
export interface OrphanArticleAdmin {
  _id: string;
  title: string;
  source: string;
  theme: string;
  gravity_score: number;
  sentiment?: string;
  elected?: string[];
  institutions?: string[];
  scraped_at: string;
  url?: string;
}

export const fetchOrphanArticles = (limit = 50) =>
  adminFetch<{ orphans: OrphanArticleAdmin[]; total: number }>(
    `/api/admin/articles/orphans?limit=${limit}`
  );

export const fetchActiveAffairsSummary = () =>
  adminFetch<{ affairs: Affair[]; total: number }>(
    '/api/admin/affairs/active-summary'
  );

export const mergeAffairs = (keepId: string, mergeIds: string[], reason?: string) =>
  adminFetch<{ success: boolean; merged: number; keep_id: string }>(
    '/api/admin/affairs/merge',
    { method: 'POST', body: JSON.stringify({ keep_id: keepId, merge_ids: mergeIds, reason }) }
  );

export const splitAffair = (sourceId: string, articleIds: string[], newTitle?: string) =>
  adminFetch<{ success: boolean; new_affair_id: string; articles_moved: number }>(
    '/api/admin/affairs/split',
    { method: 'POST', body: JSON.stringify({ source_id: sourceId, article_ids: articleIds, new_title: newTitle }) }
  );

export const linkArticleToAffair = (affairId: string, articleId: string) =>
  adminFetch<{ success: boolean }>(
    '/api/admin/affairs/link-article',
    { method: 'POST', body: JSON.stringify({ affair_id: affairId, article_id: articleId }) }
  );

export const unlinkArticleFromAffair = (affairId: string, articleId: string) =>
  adminFetch<{ success: boolean }>(
    '/api/admin/affairs/unlink-article',
    { method: 'POST', body: JSON.stringify({ affair_id: affairId, article_id: articleId }) }
  );

export const reclassifyAffair = (affairId: string, changes: Partial<{ title: string; theme: string; priority: string; status: string; entities: string[]; elected: string[] }>) =>
  adminFetch<{ success: boolean; updated_fields: string[] }>(
    `/api/admin/affairs/${affairId}/reclassify`,
    { method: 'PUT', body: JSON.stringify(changes) }
  );

export const archiveAffair = (affairId: string) =>
  adminFetch<{ success: boolean }>(
    `/api/admin/affairs/${affairId}/archive`,
    { method: 'POST' }
  );

export const fetchAdminActivityLog = (limit = 50) =>
  adminFetch<{ events: Array<{ _id: string; affair_id: string; event: string; details: Record<string, unknown>; timestamp: string }>; total: number }>(
    `/api/admin/activity-log?limit=${limit}`
  );

// --- Création de comptes par admin ---
export const adminCreateUser = (email: string, password: string, name: string, role: string) =>
  adminFetch<{ success: boolean; user: { id: string; email: string; name: string; role: string } }>(
    '/api/auth/create-user',
    { method: 'POST', body: JSON.stringify({ email, password, name, role }) }
  );

export const adminDeleteUser = (userId: string) =>
  adminFetch<{ success: boolean; message: string }>(
    `/api/auth/delete-user/${userId}`,
    { method: 'DELETE' }
  );

// --- Liens de consultation publics ---
export const createShareLink = (affairId: string) =>
  adminFetch<{ success: boolean; share_token: string; share_url: string }>(
    `/api/affairs/share/${affairId}`,
    { method: 'POST' }
  );

export const revokeShareLink = (affairId: string) =>
  adminFetch<{ success: boolean }>(
    `/api/affairs/share/${affairId}`,
    { method: 'DELETE' }
  );

// --- Accès public (pas de token) ---
export const fetchSharedAffair = (token: string) =>
  apiFetch<{
    affair: {
      id: string; title: string; description: string; theme: string;
      status: string; gravity_score: number; bmg: number; sentiment: string;
      elected: string[]; institutions: string[]; item_count: number;
      created_at: string; last_activity: string;
    };
    ai_context: AffairContext | null;
    articles: Array<{ _id: string; title: string; source: string; scraped_at: string; gravity_score: number; theme: string }>;
    total_articles: number;
  }>(`/api/affairs/shared/${token}`);

// --- Changement de mot de passe ---
export const changePassword = (currentPassword: string, newPassword: string) =>
  adminFetch<{ success: boolean; message: string }>(
    '/api/auth/change-password',
    { method: 'PUT', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }
  );

// --- Santé système (Admin) ---
export interface SystemHealthData {
  health: {
    last_scrape: string | null;
    last_enrichment: string | null;
    last_scheduler_run: string | null;
    scheduler_last_status: string;
    last_radio_capture: string | null;
    last_daily_report: string | null;
    recent_errors_24h: number;
  };
  counts: {
    articles: number;
    affairs_active: number;
    radio_transcriptions: number;
    social_posts: number;
    users: number;
  };
  timestamp: string;
}

export const fetchSystemHealth = () =>
  adminFetch<{ success: boolean } & SystemHealthData>('/api/auth/system-health');

// --- Bilans PDF ---
export const triggerDailyReport = () =>
  adminFetch<{ success: boolean; message: string }>('/api/scheduler/daily-report-now', { method: 'POST' });

export const fetchLatestReport = () =>
  `/api/scheduler/daily-report/latest`;

// --- Vérification GPT des articles liés ---
export const verifyLinkedArticles = (affairId: string, autoUnlink: boolean = false) =>
  adminFetch<{
    success: boolean;
    affair_id: string;
    total_articles: number;
    keep: string[];
    unlink: string[];
    reasons: Record<string, string>;
    auto_unlinked: number;
  }>(`/api/affairs/verify-articles/${affairId}?auto_unlink=${autoUnlink}`, { method: 'POST' });
