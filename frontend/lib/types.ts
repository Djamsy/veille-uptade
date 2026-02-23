// Emplacement: frontend/lib/types.ts

export interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
  active: boolean
  created_at: string
}

export interface Article {
  id: string
  title: string
  content: string
  url: string
  source: string
  published_date: string
  scraped_at: string
  importance_score: number
  sentiment?: SentimentAnalysis
  primary_entity?: string
  theme?: Theme
  entities?: Entity[]
  affair_id?: string
  social_monitoring?: SocialMonitoring
  mistral_analysis?: {
    called: boolean
    confidence: number
    reasoning: string
  }
}

export interface Affair {
  affaire_id: string
  theme: Theme
  primary_entity: string
  importance_score: number
  sentiment_analysis: SentimentAnalysis
  created_at: string
  last_updated: string
  article_count: number
  articles: string[]
  social_metrics?: SocialMetrics
  timeline?: TimelineEvent[]
  status: 'active' | 'monitoring' | 'closed'
  crisis_level?: 'low' | 'medium' | 'high' | 'critical'
}

export interface SentimentAnalysis {
  basic_sentiment: {
    positive: number
    negative: number
    neutral: number
    overall: 'positive' | 'negative' | 'neutral'
  }
  contextual_analysis: {
    emotions: Record<string, number>
    topics: string[]
    confidence: number
  }
  stakeholders: Array<{
    name: string
    sentiment: number
    relevance: number
  }>
}

export interface SocialMonitoring {
  platform: 'facebook' | 'instagram' | 'twitter' | 'tiktok'
  posts_count: number
  comments_count: number
  engagement_rate: number
  sentiment_distribution: {
    positive: number
    negative: number
    neutral: number
  }
  crisis_indicators: string[]
  last_scan: string
}

export interface SocialMetrics {
  total_mentions: number
  platforms: Record<string, SocialMonitoring>
  sentiment_trend: Array<{
    date: string
    sentiment: number
    engagement: number
  }>
  crisis_level: 'low' | 'medium' | 'high' | 'critical'
  alerts: Array<{
    type: string
    message: string
    severity: string
    timestamp: string
  }>
}

export type Theme = 
  | 'securite_justice' 
  | 'environnement_agriculture' 
  | 'sante_social' 
  | 'politique_institutions' 
  | 'culture_sport'
  | 'economie'

export interface Entity {
  text: string
  type: 'PERSON' | 'ORG' | 'GPE' | 'EVENT'
  confidence: number
}

export interface TimelineEvent {
  date: string
  event: string
  articles: string[]
  impact_score: number
}

export interface WebSocketMessage {
  type: 'article_update' | 'affair_update' | 'social_alert' | 'scraping_status' | 'connection'
  data: any
  timestamp: string
}

export interface DashboardStats {
  articles: {
    total: number
    today: number
    by_source: Record<string, number>
    by_theme: Record<Theme, number>
    recent: Article[]
  }
  affairs: {
    active: number
    critical: number
    by_theme: Record<Theme, number>
    recent: Affair[]
  }
  social: {
    monitoring_active: boolean
    crisis_alerts: number
    platforms_monitored: number
    recent_alerts: Array<{
      affair_id: string
      message: string
      severity: string
      timestamp: string
    }>
  }
  scraping: {
    last_run: string
    status: 'running' | 'idle' | 'error'
    next_run: string
    articles_scraped: number
  }
}

// API Response types
export interface APIResponse<T = any> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  pagination: {
    page: number
    limit: number
    total: number
    pages: number
  }
}

export interface ScrapingResult {
  success: boolean
  articles_scraped: number
  new_affairs: number
  social_monitoring_triggered: boolean
  execution_time: number
  errors?: string[]
}