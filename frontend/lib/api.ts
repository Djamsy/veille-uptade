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

// --- Storage ---
export interface StorageStats {
  data_size_mb: number;
  storage_size_mb: number;
  index_size_mb: number;
  total_used_mb: number;
  limit_mb: number;
  usage_pct: number;
  alert_level: 'ok' | 'warning' | 'high' | 'critical';
  collections: Array<{ name: string; size_mb: number; count: number }>;
  checked_at: string;
}
export const fetchStorageStats = () =>
  adminFetch<StorageStats>('/api/storage');

// --- Carte interactive ---
export interface MapCommuneItem {
  id?: string;
  title: string;
  source?: string;
  station?: string;
  summary?: string;
  theme?: string;
  gravity: number;
  sentiment?: string;
  bmg?: number;
  priority?: string;
  items?: number;
  date?: string;
}

export interface MapCommuneData {
  articles: MapCommuneItem[];
  transcriptions: MapCommuneItem[];
  affairs: MapCommuneItem[];
  stats: {
    total_items: number;
    article_count: number;
    transcription_count: number;
    affair_count: number;
    max_gravity: number;
    dominant_theme: string;
  };
}

export interface MapResponse {
  communes: Record<string, MapCommuneData>;
  period_days: number;
  total_communes_active: number;
  generated_at: string;
}

export const fetchMapData = (days = 7) =>
  adminFetch<MapResponse>(`/api/map?days=${days}`);

export const sendDigestNow = () =>
  adminFetch<{ sent: boolean }>('/api/digest/send', { method: 'POST' });

export const cleanupAffair = (affairId: string) =>
  adminFetch<{ kept: number; removed: number }>(`/api/affairs/${affairId}/cleanup`, { method: 'POST' });

export const cleanupAllAffairs = () =>
  adminFetch<{ total_removed: number }>('/api/affairs/cleanup-all', { method: 'POST' });

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
export interface SocialComment {
  author: string;
  text: string;
  likes: number;
}

export interface SocialPost {
  _id: string;
  platform: 'facebook' | 'instagram' | 'twitter' | 'tiktok';
  author: string;
  text: string;
  url: string;
  posted_at: string;
  likes: number;
  comments?: number;
  comments_count?: number;
  comment_texts?: SocialComment[];
  shares?: number;
  retweets?: number;
  replies?: number;
  views?: number;
  scraped_at: string;
  image_url?: string;
  media_type?: string;
  ai_enriched?: boolean;
  ai_relevant?: boolean;
  ai_summary?: string;
  sentiment?: string;
  opinion_commentaires?: string;
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

// --- Recherche full-text ---
export interface SearchResult {
  query: string;
  articles: Article[];
  affairs: Affair[];
  total_articles: number;
  total_affairs: number;
}

export const fetchSearch = (q: string, limit = 20) =>
  apiFetch<SearchResult>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// --- Résumé automatique ---
export interface SummarySection {
  titre: string;
  articles: Array<{
    titre: string;
    resume: string;
    gravite: string;
    communes: string[];
    sources: string[];
    contexte: string;
  }>;
}

export interface MediaSummary {
  titre: string;
  date_generation: string;
  introduction: string;
  sections: SummarySection[];
  tendances: string;
  a_surveiller: string[];
}

export interface SummaryResponse {
  period: string;
  generated_at: string;
  affairs_count: number;
  articles_count: number;
  summary: MediaSummary;
}

export const fetchSummary = (period: 'journalier' | 'hebdomadaire' = 'journalier') =>
  apiFetch<SummaryResponse>(`/api/summary?period=${period}`);

// --- Fiabilité des sources ---
export interface SourceReliability {
  source: string;
  total_articles: number;
  reliability_score: number;
  reliability_level: string;
  enrichment_rate: number;
  geo_rate: number;
  themes: string[];
  sentiment_distribution: Record<string, number>;
  avg_gravity: number;
}

export interface SourceReliabilityResponse {
  sources: SourceReliability[];
  total_sources: number;
  generated_at: string;
}

export const fetchSourceReliability = () =>
  apiFetch<SourceReliabilityResponse>('/api/sources/reliability');

// --- Radio / Capture ---
export interface RadioStream {
  key: string;
  name: string;
  original_url: string;
  working_url: string;
  url_changed: boolean;
  enabled: boolean;
  priority: number;
}

export interface RadioStreamsResponse {
  success: boolean;
  streams: RadioStream[];
}

export interface RadioHealthResult {
  key: string;
  name: string;
  section: string;
  type: string;
  url: string;
  enabled: boolean;
  status: string;
  latency_ms: number;
  content_type: string;
}

export interface RadioHealthResponse {
  results: RadioHealthResult[];
  summary: { total: number; healthy: number; degraded: number; down: number };
  checked_at: string;
}

export interface RadioCaptureResponse {
  success: boolean;
  card: Record<string, unknown>;
  used_key: string;
  resolution_reason: string;
  url_used: string;
}

export const fetchRadioStreams = () =>
  apiFetch<RadioStreamsResponse>('/api/radio/debug/streams');

export const fetchRadioHealth = () =>
  apiFetch<RadioHealthResponse>('/api/radio/health-check');

export const triggerRadioCapture = (section: string, duration = 20) =>
  apiFetch<RadioCaptureResponse>(`/api/radio/capture?section=${encodeURIComponent(section)}&duration=${duration}`, { method: 'POST' });

export const fetchRadioToday = () =>
  apiFetch<{ cards: Array<Record<string, unknown>>; count: number }>('/api/radio/cards/today');

// ============================================================
// VEILLE — Briefing, Trending, Coverage, Watchlist
// ============================================================

export interface BriefingAffair {
  _id: string;
  title: string;
  gravity_score: number;
  theme: string;
  status: string;
  item_count: number;
  sources: string[];
  commune?: string;
  priority?: string;
  created_at?: string;
  last_activity?: string;
  bmg?: number;
}

export interface RadioHighlight {
  stream: string;
  summary: string;
  topic: string;
  gravity: number;
  captured_at: string;
}

export interface TrendingAffair {
  _id: string;
  title: string;
  gravity_score: number;
  theme: string;
  velocity: number;
  source_spread: number;
  trend_score: number;
  is_new: boolean;
  priority: string;
}

export interface WatchlistHit {
  keyword: string;
  category: string;
  articles_matched: number;
  radio_matched: number;
  top_articles: Array<{ title: string; source: string; gravity: number }>;
  top_radio: Array<{ stream: string; topic: string }>;
}

export interface CoverageGap {
  affair_title: string;
  gravity: number;
  covered_by: string[];
  missing_from: string[];
}

export interface BriefingResponse {
  success: boolean;
  briefing: {
    generated_at: string;
    period_hours: number;
    top_affairs: BriefingAffair[];
    new_affairs: BriefingAffair[];
    radio_highlights: RadioHighlight[];
    trending: TrendingAffair[];
    coverage: {
      sources_active: string[];
      source_theme_matrix: Record<string, Record<string, number>>;
      coverage_gaps: CoverageGap[];
      total_sources: number;
      total_articles: number;
    };
    watchlist_hits: WatchlistHit[];
    stats: {
      period_hours: number;
      total_active_affairs: number;
      new_affairs_count: number;
      articles_count: number;
      radio_captures_count: number;
      sources_active: Record<string, number>;
      themes_distribution: Record<string, number>;
      sentiment_distribution: Record<string, number>;
    };
  };
}

export interface TrendingResponse {
  success: boolean;
  trending: TrendingAffair[];
  period_hours: number;
}

export interface WatchlistItem {
  _id: string;
  keyword: string;
  keyword_display: string;
  category: string;
  notify_telegram: boolean;
  min_gravity: number;
  hit_count: number;
  last_hit: string | null;
  created_at: string;
}

export interface QuickSummary {
  success: boolean;
  summary: {
    active_affairs: number;
    hot_affairs: number;
    articles_today: number;
    radio_today: number;
    latest_affair: { title: string; gravity: number } | null;
    timestamp: string;
  };
}

export const fetchBriefing = (hours = 24) =>
  apiFetch<BriefingResponse>(`/api/veille/briefing?hours=${hours}`);

export const sendBriefingTelegram = (hours = 24) =>
  apiFetch<{ success: boolean; message: string }>(`/api/veille/briefing/telegram?hours=${hours}`, { method: 'POST' });

export const fetchTrending = (hours = 12) =>
  apiFetch<TrendingResponse>(`/api/veille/trending?hours=${hours}`);

export const fetchCoverage = (days = 1) =>
  apiFetch<{ success: boolean; coverage: Record<string, unknown> }>(`/api/veille/coverage?days=${days}`);

export const fetchWatchlist = () =>
  apiFetch<{ success: boolean; watchlist: WatchlistItem[]; total: number }>('/api/veille/watchlist');

export const addWatchlistKeyword = (keyword: string, category = 'general', notify = true, minGravity = 0) =>
  apiFetch<{ success: boolean; item: WatchlistItem }>('/api/veille/watchlist', {
    method: 'POST',
    body: JSON.stringify({ keyword, category, notify_telegram: notify, min_gravity: minGravity }),
  });

export const removeWatchlistKeyword = (keyword: string) =>
  apiFetch<{ success: boolean }>(`/api/veille/watchlist?keyword=${encodeURIComponent(keyword)}`, { method: 'DELETE' });

export const fetchQuickSummary = () =>
  apiFetch<QuickSummary>('/api/veille/quick-summary');

// ============================================================
// CAMPAGNES RS
// ============================================================

export interface Campaign {
  _id: string;
  name: string;
  slug: string;
  description: string;
  keywords: string[];
  start_date: string;
  end_date: string | null;
  status: string;
  created_at: string;
  post_count: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_clicks: number;
  total_reach: number;
  ai_analysis?: Record<string, unknown>;
  analyzed_at?: string;
}

export interface CampaignPost {
  _id: string;
  title: string;
  body: string;
  hashtags: string[];
  media_url: string;
  media_type: string;
  campaign_id: string;
  campaign_name: string;
  published_at: string;
  stats: { views: number; likes: number; comments: number; clicks: number; reach: number };
  platform_stats: Record<string, { views: number; likes: number; comments: number; clicks: number; reach: number }>;
  sentiment?: { global: string; score: number } | null;
  ai_analysis?: Record<string, unknown> | null;
}

export const fetchCampaigns = (status?: string) =>
  apiFetch<{ campaigns: Campaign[]; total: number }>(`/api/campaigns${status ? `?status=${status}` : ''}`);

export const createCampaign = (data: { name: string; description?: string; keywords?: string[]; start_date?: string; end_date?: string }) =>
  apiFetch<{ ok: boolean; campaign: Campaign }>('/api/campaigns', { method: 'POST', body: JSON.stringify(data) });

export const fetchCampaignDetail = (id: string) =>
  apiFetch<{ campaign: Campaign; posts: CampaignPost[] }>(`/api/campaigns/${id}`);

export const updateCampaign = (id: string, data: Record<string, unknown>) =>
  apiFetch<{ ok: boolean }>(`/api/campaigns/${id}`, { method: 'PUT', body: JSON.stringify(data) });

export const analyzeCampaign = (id: string) =>
  apiFetch<{ ok: boolean; analysis: Record<string, unknown> }>(`/api/campaigns/${id}/analyze`, { method: 'POST' });

export const compareCampaigns = (a: string, b: string) =>
  apiFetch<{ ok: boolean; comparison: Record<string, unknown> }>('/api/campaigns/compare', {
    method: 'POST', body: JSON.stringify({ campaign_a: a, campaign_b: b }),
  });

export const fetchCampaignPosts = (campaignId: string, limit = 50) =>
  apiFetch<{ posts: CampaignPost[]; total: number }>(`/api/campaigns/${campaignId}/posts?limit=${limit}`);

export const publishPost = async (data: { text: string; campaign_id?: string; media?: File }) => {
  const formData = new FormData();
  formData.append('text', data.text);
  if (data.campaign_id) formData.append('campaign_id', data.campaign_id);
  if (data.media) formData.append('media', data.media);

  const res = await fetch(`${BACKEND_URL}/api/publish`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`Erreur publication: ${res.status}`);
  return res.json() as Promise<{ ok: boolean; post_id: string; campaign: string; platforms: number; media_uploaded: boolean }>;
};

export interface ServiceStatus {
  bot_configured: boolean;
  buffer_configured: boolean;
  cloudinary_configured: boolean;
  mistral_configured: boolean;
}

export const fetchPublicationStatus = () =>
  apiFetch<ServiceStatus>('/api/publication-bot/status');

export const fetchSocialStatsStatus = () =>
  apiFetch<{ configured: boolean; platforms: string[]; frequency: string }>('/api/social-stats/status');
