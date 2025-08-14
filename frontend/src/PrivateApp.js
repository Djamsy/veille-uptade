// src/PrivateApp.js
import React, { useState, useEffect } from 'react';
import './App.css';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip, Legend, Filler
} from 'chart.js';
import { Bar, Line, Doughnut } from 'react-chartjs-2';

// Enregistrer les composants Chart.js
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

// --- Helpers affichage IA (normalisation + markdown léger) ---
const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[ch]));

// Ajoute des sauts de ligne quand GPT renvoie tout sur une seule ligne
const normalizeAIText = (raw) => {
  if (!raw) return "";
  let t = String(raw).trim();

  // Si pas (ou peu) de retours à la ligne, on en crée avant chaque **Bloc** et puces
  const fewBreaks = (t.match(/\n/g) || []).length < 2;
  if (fewBreaks) {
    // retour avant chaque **XXX** (sauf si tout au début)
    t = t.replace(/(\s+)?\*\*([^\*]+)\*\*/g, (m, sp, title, i) => `${i ? "\n" : ""}**${title}**`);
    // transformer " - " et puces en vraies lignes
    t = t.replace(/\s[-–—]\s+/g, "\n- ");
    t = t.replace(/[•▪︎▫︎►▶︎◆■□]\s*/g, () => `\n- `);
  }

  // Normalisations douces
  t = t
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")               // pas plus de 1 ligne vide
    .replace(/^\s*-\s*/gm, "• ");             // puces visuelles
  return t;
};

// Rendu HTML simple (titres ###, **gras**, lignes et puces)
const renderAIText = (text) => {
  const input = normalizeAIText(text);
  let html = escapeHtml(input);

  // Titres
  html = html.replace(/^###\s+(.*)$/gm, '<div class="ai-h3">$1</div>');
  html = html.replace(/^##\s+(.*)$/gm,  '<div class="ai-h2">$1</div>');
  html = html.replace(/^#\s+(.*)$/gm,   '<div class="ai-h1">$1</div>');

  // Gras
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Puces (lignes commençant par • )
  html = html.replace(/^(?:•\s+.*)$/gm, (line) =>
    `<div class="ai-li">${line.replace(/^•\s+/, "")}</div>`);

  // Paragraphes + sauts
  html = html.replace(/\n{2,}/g, '</p><p>');
  html = html.replace(/\n/g, '<br/>');
  html = `<p>${html}</p>`;

  return (
    <div
      className="ai-markdown"
      style={{ lineHeight: 1.8, whiteSpace: 'normal', color: '#1f2937' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};

// --- Global styles to improve AI text readability (paragraphs, spacing, bullets) ---
const GlobalStyles = () => (
  <style>{`
    .transcription-explication,
    .extract-content,
    .article-explication {
      white-space: pre-line;
      line-height: 1.7;
    }
    .ai-summary p { margin: 0 0 0.75rem 0; line-height: 1.7; }
    .ai-markdown .ai-li { margin-left: 1rem; }
    .ai-markdown strong { font-weight: 700; }
  `}</style>
);

// Composants graphiques
const SourceChart = ({ data }) => {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#f9fafb',
        bodyColor: '#f9fafb',
        borderColor: 'rgba(75, 85, 99, 0.3)',
        borderWidth: 1
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: 'rgba(75, 85, 99, 0.1)'
        },
        ticks: {
          color: '#6b7280'
        }
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: '#6b7280',
          maxRotation: 45
        }
      }
    }
  };
  return <Doughnut data={data} options={options} />;
};

const TimelineChart = ({ data }) => {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#f9fafb',
        bodyColor: '#f9fafb',
        borderColor: 'rgba(75, 85, 99, 0.3)',
        borderWidth: 1
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: 'rgba(75, 85, 99, 0.1)'
        },
        ticks: {
          color: '#6b7280'
        }
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: '#6b7280',
          maxRotation: 45
        }
      }
    },
    interaction: {
      intersect: false,
      mode: 'index'
    }
  };

  return <Line data={data} options={options} />;
};

const SentimentChart = ({ data }) => {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: {
          color: '#4b5563',
          usePointStyle: true
        }
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#f9fafb',
        bodyColor: '#f9fafb',
        borderColor: 'rgba(75, 85, 99, 0.3)',
        borderWidth: 1
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        stacked: true,
        grid: {
          color: 'rgba(75, 85, 99, 0.1)'
        },
        ticks: {
          color: '#6b7280'
        }
      },
      x: {
        stacked: true,
        grid: {
          display: false
        },
        ticks: {
          color: '#6b7280',
          maxRotation: 45
        }
      }
    }
  };

  return <Bar data={data} options={options} />;
};


const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';


// --- Analytics normalization and safe defaults ---
const EMPTY_DATASETS = [{ label: 'Aucune donnée', data: [] }];
const EMPTY_ANALYTICS = {
  labels: [],
  series: [],
  datasets: EMPTY_DATASETS,
  data: { labels: [], series: [], datasets: EMPTY_DATASETS }
};

function normalizeAnalytics(resp) {
  const r = (resp && (resp.data || resp)) || {};
  // Try common label keys
  const labels =
    Array.isArray(r.labels) ? r.labels :
    Array.isArray(r.dates) ? r.dates :
    [];

  // Build a generic "series" (single array of numbers) for simple charts
  let series = [];
  if (Array.isArray(r.series) && r.series.every(v => typeof v === 'number')) {
    series = r.series;
  } else if (Array.isArray(r.counts)) {
    series = r.counts;
  } else if (Array.isArray(r.values)) {
    series = r.values;
  } else if (Array.isArray(r.datasets) && Array.isArray(r.datasets[0]?.data)) {
    series = r.datasets[0].data;
  } else {
    series = new Array(labels.length).fill(0);
  }

  // Always expose a datasets array for Chart.js
  const datasets = Array.isArray(r.datasets) && r.datasets.length > 0
    ? r.datasets
    : [{ label: r.label || 'Valeurs', data: series }];

  return {
    labels,
    series,
    datasets,
    data: { labels, series, datasets } // mirror under data.* for frontends that expect it
  };
}
// --- End analytics normalization ---

// --- Reaction prediction normalization (safe defaults) ---
const DEFAULT_REACTION = {
  overall_reaction: 'neutral',
  breakdown: { positive: 0, neutral: 1, negative: 0 },
  confidence: 0,
  model: 'local-baseline',
  note: null,
};

function normalizeReactionResponse(json) {
  const p = json?.prediction ?? json ?? {};
  return {
    overall_reaction: p?.overall_reaction ?? DEFAULT_REACTION.overall_reaction,
    breakdown: {
      positive: Number(p?.breakdown?.positive ?? 0),
      neutral: Number(p?.breakdown?.neutral ?? 1),
      negative: Number(p?.breakdown?.negative ?? 0),
    },
    confidence: Number.isFinite(p?.confidence) ? p.confidence : DEFAULT_REACTION.confidence,
    model: p?.model ?? DEFAULT_REACTION.model,
    note: p?.note ?? null,
  };
}
// --- End reaction prediction normalization ---
// --- Helper: format AI summaries into readable HTML ---
function prettySummary(raw) {
  if (!raw) return "";
  let s = String(raw).replace(/\r/g, "").trim();

  // Supprimer les titres markdown (### ...)
  s = s.replace(/(^|\n)\s*#{1,6}\s*/g, "\n\n");

  // Saut de ligne avant les sections en gras
  s = s.replace(/(\*\*[^*][^*]+\*\*)/g, (m) => `\n\n${m} `);

  // Tirets → tirets longs
  s = s.replace(/\s-\s/g, " — ");

  // **gras** → <strong>
  s = s.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // Paragraphes
  const paragraphs = s.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  return paragraphs.map(p => `<p>${p}</p>`).join("");
}
// --- End helper ---
function PrivateApp() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardStats, setDashboardStats] = useState({});
  // ... (tous les autres useState / useEffect ici, à l’intérieur de App)
  const [articles, setArticles] = useState([]);
  const [transcriptions, setTranscriptions] = useState([]);
  const [digest, setDigest] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState({});
  const [loading, setLoading] = useState(false);
  const [backgroundTasks, setBackgroundTasks] = useState({});
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [error, setError] = useState(null);
  
  // Nouveaux états pour la recherche et les commentaires
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchSuggestions, setSearchSuggestions] = useState([]);
  const [comments, setComments] = useState([]);
  const [commentsAnalysis, setCommentsAnalysis] = useState(null);
  const [socialStats, setSocialStats] = useState({});
  
  // États pour la recherche sociale
  const [socialSearchQuery, setSocialSearchQuery] = useState('');
  const [socialSearchResults, setSocialSearchResults] = useState(null);
  const [socialSearchLoading, setSocialSearchLoading] = useState(false);
  
  // États pour les transcriptions par sections
  const [transcriptionSections, setTranscriptionSections] = useState({
    "7H RCI": [],
    "7H Guadeloupe Première": [],
    "Autres": []
  });
  const [transcriptionStatus, setTranscriptionStatus] = useState({
    sections: {},
    global_status: { any_in_progress: false, total_sections: 2, active_sections: 0 }
  });
  const [socialSearchError, setSocialSearchError] = useState(null);
  
  // États pour la recherche automatique
  const [autoSearchCompleted, setAutoSearchCompleted] = useState(false);
  const [autoSearchResults, setAutoSearchResults] = useState({});

  // États pour l'analyse de sentiment et prédiction des réactions
  const [sentimentText, setSentimentText] = useState('');
  const [sentimentResult, setSentimentResult] = useState(null);
  const [sentimentLoading, setSentimentLoading] = useState(false);
  const [reactionPrediction, setReactionPrediction] = useState(DEFAULT_REACTION);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [sentimentMode, setSentimentMode] = useState('sync'); // 'sync' ou 'async'

  // États pour les filtres et analytics
  const [filters, setFilters] = useState({
    dateStart: '',
    dateEnd: '',
    source: 'all',
    searchText: '',
    sortBy: 'date_desc'
  });
  const [availableSources, setAvailableSources] = useState([]);
  const [filteredArticles, setFilteredArticles] = useState([]);
const [pagination, setPagination] = useState({ total: 0, offset: 0, returned: 0, hasMore: false });
const [analyticsData, setAnalyticsData] = useState({
  sourceChart: EMPTY_ANALYTICS,
  timelineChart: EMPTY_ANALYTICS,
  sentimentChart: EMPTY_ANALYTICS,
  dashboardMetrics: {}
});
  const [showAnalytics, setShowAnalytics] = useState(false);
  
  // États pour le mobile
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  
  // Fermer le menu mobile quand on change d'onglet
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setMobileMenuOpen(false);
    
    // Logique spécifique selon l'onglet
    if (tabId === 'search') {
      loadSearchSuggestions();
    } else if (tabId === 'comments') {
      loadComments();
      loadSocialStats();
    }
  };

  // Fonction pour obtenir le logo d'un site (version corrigée)
  const getSiteLogo = (source) => {
    const sourceMap = {
      'France-Antilles Guadeloupe': {
        logo: `https://www.google.com/s2/favicons?domain=guadeloupe.franceantilles.fr&sz=64`,
        fallback: 'FA',
        color: '#dc2626',
        bg: 'rgba(220, 38, 38, 0.1)',
        borderColor: 'rgba(220, 38, 38, 0.3)'
      },
      'RCI Guadeloupe': {
        logo: `https://www.google.com/s2/favicons?domain=rci.fm&sz=64`,
        fallback: 'RCI',
        color: '#2563eb',
        bg: 'rgba(37, 99, 235, 0.1)',
        borderColor: 'rgba(37, 99, 235, 0.3)'
      },
      'La 1ère Guadeloupe': {
        logo: `https://www.google.com/s2/favicons?domain=la1ere.francetvinfo.fr&sz=64`,
        fallback: '1ère',
        color: '#059669',
        bg: 'rgba(5, 150, 105, 0.1)',
        borderColor: 'rgba(5, 150, 105, 0.3)'
      },
      'KaribInfo': {
        logo: `https://www.google.com/s2/favicons?domain=karibinfo.com&sz=64`,
        fallback: 'KI',
        color: '#ea580c',
        bg: 'rgba(234, 88, 12, 0.1)',
        borderColor: 'rgba(234, 88, 12, 0.3)'
      }
    };

    // Recherche flexible par nom de source
    const sourceKey = Object.keys(sourceMap).find(key => 
      source.toLowerCase().includes(key.toLowerCase()) || 
      key.toLowerCase().includes(source.toLowerCase()) ||
      source.toLowerCase().includes('france') && key.includes('France') ||
      source.toLowerCase().includes('rci') && key.includes('RCI') ||
      source.toLowerCase().includes('première') && key.includes('1ère') ||
      source.toLowerCase().includes('1ere') && key.includes('1ère') ||
      source.toLowerCase().includes('karib') && key.includes('Karib')
    );

    if (sourceKey) {
      return sourceMap[sourceKey];
    }

    // Fallback générique
    return {
      logo: null,
      fallback: source.substring(0, 2).toUpperCase(),
      color: '#6b7280',
      bg: 'rgba(107, 114, 128, 0.1)',
      borderColor: 'rgba(107, 114, 128, 0.3)'
    };
  };

  // Logo de l'application Veille Média Guadeloupe
  const AppLogo = ({ size = 40 }) => {
    return (
      <div 
        className="app-logo"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: '12px',
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: `${Math.max(size * 0.4, 14)}px`,
          fontWeight: '700',
          color: 'white',
          boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
          transition: 'all 0.3s ease',
          position: 'relative',
          overflow: 'hidden'
        }}
        title="Veille Média Guadeloupe"
      >
        {/* Icône Guadeloupe stylisée */}
        <span style={{
          background: 'linear-gradient(45deg, #ffffff, #e0e7ff)',
          backgroundClip: 'text',
          webkitBackgroundClip: 'text',
          webkitTextFillColor: 'transparent',
          fontFamily: 'Inter, sans-serif',
          letterSpacing: '-1px'
        }}>
          🏝️
        </span>
        
        {/* Effet de brillance */}
        <div style={{
          position: 'absolute',
          top: '0',
          left: '-100%',
          width: '100%',
          height: '100%',
          background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)',
          animation: 'logo-shine 3s ease-in-out infinite'
        }} />
      </div>
    );
  };

  // Composant amélioré pour l'analyse de sentiment avec recommandations
  const EnhancedSentimentAnalysis = ({ analysis }) => {
    if (!analysis) return null;

    const getSentimentConfig = (polarity) => {
      const configs = {
        positive: {
          color: '#10b981',
          bgColor: 'rgba(16, 185, 129, 0.1)',
          borderColor: 'rgba(16, 185, 129, 0.3)',
          emoji: '😊',
          label: 'Positif',
          textColor: '#059669'
        },
        negative: {
          color: '#ef4444',
          bgColor: 'rgba(239, 68, 68, 0.1)',
          borderColor: 'rgba(239, 68, 68, 0.3)',
          emoji: '😞',
          label: 'Négatif',
          textColor: '#dc2626'
        },
        neutral: {
          color: '#6b7280',
          bgColor: 'rgba(107, 114, 128, 0.1)',
          borderColor: 'rgba(107, 114, 128, 0.3)',
          emoji: '😐',
          label: 'Neutre',
          textColor: '#4b5563'
        }
      };
      return configs[polarity] || configs.neutral;
    };

    const getRecommendations = (analysis) => {
      const recommendations = [];
      const { basic_sentiment, contextual_analysis } = analysis;
      
      // Recommandations basées sur le sentiment
      if (basic_sentiment.polarity === 'negative' && basic_sentiment.confidence > 0.7) {
        recommendations.push({
          type: 'alert',
          priority: 'high',
          icon: '⚠️',
          title: 'Surveillance Renforcée',
          action: 'Surveiller l\'évolution de cette actualité et préparer une réponse si nécessaire'
        });
      }
      
      if (basic_sentiment.polarity === 'positive' && basic_sentiment.confidence > 0.7) {
        recommendations.push({
          type: 'opportunity',
          priority: 'medium',
          icon: '📈',
          title: 'Opportunité de Communication',
          action: 'Capitaliser sur cette actualité positive pour améliorer l\'image'
        });
      }
      
      // Recommandations basées sur l'urgence
      if (contextual_analysis.urgency_level === 'high') {
        recommendations.push({
          type: 'urgent',
          priority: 'high',
          icon: '🚨',
          title: 'Action Immédiate',
          action: 'Préparer une réponse dans les 2-4 heures prochaines'
        });
      }
      
      // Recommandations basées sur l'impact local
      if (contextual_analysis.local_impact) {
        recommendations.push({
          type: 'local',
          priority: 'medium',
          icon: '🏝️',
          title: 'Impact Local Identifié',
          action: 'Informer les services concernés et préparer une communication locale'
        });
      }
      
      // Recommandations basées sur les parties prenantes
      if (analysis.stakeholders.personalities.length > 0) {
        recommendations.push({
          type: 'stakeholder',
          priority: 'medium',
          icon: '👥',
          title: 'Personnalités Impliquées',
          action: 'Coordonner avec les équipes de communication des personnalités mentionnées'
        });
      }
      
      if (recommendations.length === 0) {
        recommendations.push({
          type: 'monitor',
          priority: 'low',
          icon: '👁️',
          title: 'Surveillance Standard',
          action: 'Continuer la surveillance normale de cette actualité'
        });
      }
      
      return recommendations;
    };

    const config = getSentimentConfig(analysis.basic_sentiment.polarity);
    const recommendations = getRecommendations(analysis);
    const confidencePercent = Math.round(analysis.basic_sentiment.confidence * 100);
    
    return (
      <div className="enhanced-sentiment-container">
        {/* Header avec score principal */}
        <div className="sentiment-header" style={{
          background: config.bgColor,
          border: `2px solid ${config.borderColor}`,
          borderRadius: '16px',
          padding: '2rem',
          marginBottom: '2rem',
          display: 'flex',
          alignItems: 'center',
          gap: '2rem'
        }}>
          <div className="sentiment-emoji" style={{
            fontSize: '4rem',
            background: `linear-gradient(135deg, ${config.color}, ${config.color}aa)`,
            borderRadius: '50%',
            width: '100px',
            height: '100px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: `0 8px 32px ${config.color}40`
          }}>
            {config.emoji}
          </div>
          
          <div className="sentiment-details" style={{ flex: 1 }}>
            <h3 style={{ 
              margin: 0, 
              fontSize: '2rem', 
              fontWeight: '700',
              color: config.textColor,
              marginBottom: '0.5rem'
            }}>
              Sentiment {config.label}
            </h3>
            
            <div className="sentiment-metrics" style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: '1rem',
              marginTop: '1rem'
            }}>
              <div className="metric">
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Score</div>
                <div style={{ fontSize: '1.25rem', fontWeight: '600', color: config.textColor }}>
                  {analysis.basic_sentiment.score > 0 ? '+' : ''}{analysis.basic_sentiment.score}
                </div>
              </div>
              
              <div className="metric">
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Confiance</div>
                <div style={{ fontSize: '1.25rem', fontWeight: '600', color: config.textColor }}>
                  {confidencePercent}%
                </div>
              </div>
              
              <div className="metric">
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Intensité</div>
                <div style={{ fontSize: '1.25rem', fontWeight: '600', color: config.textColor }}>
                  {analysis.basic_sentiment.intensity}
                </div>
              </div>
              
              <div className="metric">
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>Urgence</div>
                <div style={{ fontSize: '1.25rem', fontWeight: '600', color: config.textColor }}>
                  {analysis.contextual_analysis.urgency_level}
                </div>
              </div>
            </div>
          </div>
        </div>
        
        {/* Recommandations d'actions */}
        <div className="recommendations-section" style={{ marginBottom: '2rem' }}>
          <h4 style={{ 
            fontSize: '1.5rem', 
            fontWeight: '600', 
            color: '#1f2937', 
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            💡 Recommandations d'Actions
          </h4>
          
          <div className="recommendations-grid" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '1rem'
          }}>
            {recommendations.map((rec, index) => {
              const priorityColors = {
                high: { bg: 'rgba(239, 68, 68, 0.1)', border: '#ef4444', text: '#dc2626' },
                medium: { bg: 'rgba(245, 158, 11, 0.1)', border: '#f59e0b', text: '#d97706' },
                low: { bg: 'rgba(59, 130, 246, 0.1)', border: '#3b82f6', text: '#2563eb' }
              };
              const colors = priorityColors[rec.priority];
              
              return (
                <div key={index} className="recommendation-card" style={{
                  background: colors.bg,
                  border: `2px solid ${colors.border}40`,
                  borderRadius: '12px',
                  padding: '1.5rem',
                  transition: 'all 0.3s ease'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '1rem'
                  }}>
                    <div style={{
                      fontSize: '2rem',
                      flexShrink: 0
                    }}>
                      {rec.icon}
                    </div>
                    
                    <div style={{ flex: 1 }}>
                      <h5 style={{
                        margin: 0,
                        fontSize: '1.1rem',
                        fontWeight: '600',
                        color: colors.text,
                        marginBottom: '0.5rem'
                      }}>
                        {rec.title}
                      </h5>
                      
                      <p style={{
                        margin: 0,
                        fontSize: '0.9rem',
                        color: '#4b5563',
                        lineHeight: '1.5'
                      }}>
                        {rec.action}
                      </p>
                      
                      <div style={{
                        marginTop: '0.75rem',
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '0.25rem 0.75rem',
                        background: colors.border + '20',
                        borderRadius: '20px',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        color: colors.text,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em'
                      }}>
                        Priorité {rec.priority === 'high' ? 'Haute' : rec.priority === 'medium' ? 'Moyenne' : 'Basse'}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Détails contextuels */}
        {analysis.contextual_analysis.guadeloupe_relevance && (
          <div className="contextual-details" style={{
            background: 'rgba(59, 130, 246, 0.05)',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            borderRadius: '12px',
            padding: '1.5rem',
            marginBottom: '1rem'
          }}>
            <h5 style={{
              margin: 0,
              fontSize: '1.2rem',
              fontWeight: '600',
              color: '#2563eb',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}>
              🏝️ Contexte Guadeloupéen
            </h5>
            
            <p style={{
              margin: 0,
              fontSize: '1rem',
              color: '#1f2937',
              lineHeight: '1.6',
              marginBottom: '1rem'
            }}>
              {analysis.contextual_analysis.guadeloupe_relevance}
            </p>
            
            {analysis.contextual_analysis.local_impact && (
              <div style={{
                padding: '1rem',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                borderRadius: '8px'
              }}>
                <strong style={{ color: '#059669' }}>Impact local identifié :</strong>
                <span style={{ marginLeft: '0.5rem', color: '#1f2937' }}>
                  {analysis.contextual_analysis.local_impact}
                </span>
              </div>
            )}
          </div>
        )}
        
        {/* Parties prenantes */}
        {(analysis.stakeholders.personalities.length > 0 || analysis.stakeholders.institutions.length > 0) && (
          <div className="stakeholders-section" style={{
            background: 'rgba(139, 92, 246, 0.05)',
            border: '1px solid rgba(139, 92, 246, 0.2)',
            borderRadius: '12px',
            padding: '1.5rem'
          }}>
            <h5 style={{
              margin: 0,
              fontSize: '1.2rem',
              fontWeight: '600',
              color: '#7c3aed',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}>
              👥 Parties Prenantes Identifiées
            </h5>
            
            {analysis.stakeholders.personalities.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <h6 style={{ 
                  fontSize: '1rem', 
                  fontWeight: '600', 
                  color: '#4b5563', 
                  marginBottom: '0.5rem' 
                }}>
                  Personnalités :
                </h6>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {analysis.stakeholders.personalities.map((person, i) => (
                    <span key={i} style={{
                      background: 'rgba(139, 92, 246, 0.2)',
                      color: '#7c3aed',
                      padding: '0.25rem 0.75rem',
                      borderRadius: '20px',
                      fontSize: '0.875rem',
                      fontWeight: '500'
                    }}>
                      {person}
                    </span>
                  ))}
                </div>
              </div>
            )}
            
            {analysis.stakeholders.institutions.length > 0 && (
              <div>
                <h6 style={{ 
                  fontSize: '1rem', 
                  fontWeight: '600', 
                  color: '#4b5563', 
                  marginBottom: '0.5rem' 
                }}>
                  Institutions :
                </h6>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {analysis.stakeholders.institutions.map((inst, i) => (
                    <span key={i} style={{
                      background: 'rgba(139, 92, 246, 0.2)',
                      color: '#7c3aed',
                      padding: '0.25rem 0.75rem',
                      borderRadius: '20px',
                      fontSize: '0.875rem',
                      fontWeight: '500'
                    }}>
                      {inst}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };
  const SourceLogo = ({ source, size = 32 }) => {
    const [imageError, setImageError] = useState(false);
    const [imageLoaded, setImageLoaded] = useState(false);
    const siteInfo = getSiteLogo(source);

    const logoStyle = {
      width: `${size}px`,
      height: `${size}px`,
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: `${Math.max(size * 0.25, 10)}px`,
      fontWeight: '700',
      flexShrink: 0,
      border: `2px solid ${siteInfo.borderColor}`,
      background: siteInfo.bg,
      color: siteInfo.color,
      position: 'relative',
      overflow: 'hidden',
      transition: 'all 0.3s ease',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
    };

    // Toujours afficher le fallback avec initiales pour une meilleure visibilité
    return (
      <div style={logoStyle} title={`Source: ${source}`}>
        <span style={{ 
          letterSpacing: '-0.5px',
          textShadow: '0 1px 2px rgba(0,0,0,0.1)',
          fontFamily: 'Inter, sans-serif'
        }}>
          {siteInfo.fallback}
        </span>
        
        {/* Tentative de chargement du logo en arrière-plan */}
        {siteInfo.logo && !imageError && (
          <img
            src={siteInfo.logo}
            alt={`Logo ${source}`}
            style={{
              position: 'absolute',
              width: '70%',
              height: '70%',
              objectFit: 'contain',
              opacity: imageLoaded ? 1 : 0,
              transition: 'opacity 0.3s ease',
              zIndex: 1
            }}
            onLoad={() => setImageLoaded(true)}
            onError={() => setImageError(true)}
            loading="lazy"
          />
        )}
      </div>
    );
  };

  // Fonction utilitaire pour les appels API avec timeout et gestion d'erreur
  const apiCall = async (url, options = {}) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 secondes timeout

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error('Délai d\'attente dépassé (30s)');
      }
      throw error;
    }
  };

  // Charger les statistiques du dashboard avec cache
  const loadDashboardStats = async () => {
    try {
      const data = await apiCall(`${BACKEND_URL}/api/dashboard-stats`);
      if (data.success) {
        setDashboardStats(data.stats);
      }
    } catch (error) {
      console.error('Erreur chargement stats:', error);
      setError('Erreur chargement des statistiques');
    }
  };

  // Charger les données selon l'onglet actif avec cache intelligent
  const loadTabData = async (tab, date = null, force = false) => {
    if (loading) return; // Éviter les appels multiples
    
    setLoading(true);
    setError(null);
    
    try {
      const targetDate = date || selectedDate;
      
      switch (tab) {
        case 'articles':
          const articlesUrl = targetDate !== new Date().toISOString().split('T')[0] 
            ? `${BACKEND_URL}/api/articles/${targetDate}`
            : `${BACKEND_URL}/api/articles`;
          
          const articlesData = await apiCall(articlesUrl);
          if (articlesData.success) {
            setArticles(articlesData.articles);
          }
          break;
          
        case 'transcription':
          const transcriptionsUrl = targetDate !== new Date().toISOString().split('T')[0]
            ? `${BACKEND_URL}/api/transcriptions/${targetDate}`
            : `${BACKEND_URL}/api/transcriptions`;
          
          const transcriptionsData = await apiCall(transcriptionsUrl);
          if (transcriptionsData.success) {
            setTranscriptions(transcriptionsData.transcriptions);
          }
          break;
          
        case 'digest':
          const digestUrl = targetDate !== new Date().toISOString().split('T')[0]
            ? `${BACKEND_URL}/api/digest/${targetDate}`
            : `${BACKEND_URL}/api/digest`;
          
          const digestData = await apiCall(digestUrl);
          if (digestData.success) {
            setDigest(digestData.digest);
          } else {
            setDigest(null);
          }
          break;
          
        case 'scheduler':
          const schedulerData = await apiCall(`${BACKEND_URL}/api/scheduler/status`);
          if (schedulerData.success) {
            setSchedulerStatus(schedulerData);
          }
          break;
          
        case 'search':
          // Charger les suggestions de recherche si pas de query spécifique
          if (!searchQuery || searchQuery.trim().length < 2) {
            await loadSearchSuggestions();
          } else {
            // Effectuer une recherche si une query existe
            await handleSearch(searchQuery);
          }
          break;
          
        case 'comments':
          // Charger les commentaires et les stats sociales
          await loadComments();
          await loadSocialStats();
          break;
          
        case 'analytics':
          // Charger les données d'analytics
          await loadAnalyticsData();
          break;
      }
    } catch (error) {
      console.error(`Erreur chargement ${tab}:`, error);
      setError(`Erreur chargement ${tab}: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardStats();
    loadAvailableSources(); // Charger les sources disponibles
    
    if (activeTab !== 'dashboard') {
      loadTabData(activeTab);
    }
    
    // Charger des données spécifiques pour certains onglets
    if (activeTab === 'search') {
      loadSearchSuggestions();
    } else if (activeTab === 'comments') {
      loadSocialStats();
    } else if (activeTab === 'articles') {
      loadFilteredArticles(); // Utiliser le nouveau système de filtrage
    } else if (activeTab === 'analytics') {
      loadAnalyticsData();
    } else if (activeTab === 'transcription') {
      loadTranscriptionSections();
      loadTranscriptionStatus();
      
      // Auto-actualisation des transcriptions toutes les 30 secondes
      const transcriptionInterval = setInterval(() => {
        loadTranscriptionSections();
        loadTranscriptionStatus();
      }, 30000); // 30 secondes
      
      // Nettoyer l'interval quand on quitte l'onglet
      return () => clearInterval(transcriptionInterval);
    }
    
    // Lancer la recherche automatique au premier chargement
    if (!autoSearchCompleted) {
      performAutoSearch();
    }
  }, [activeTab, selectedDate, autoSearchCompleted]);

  // Effet pour les animations au scroll avec approche narrative
  useEffect(() => {
    const observerOptions = {
      threshold: 0.1,
      rootMargin: '0px 0px -100px 0px'
    };

    const staggerObserverOptions = {
      threshold: 0.2,
      rootMargin: '0px 0px -50px 0px'
    };

    // Observer pour les éléments simples
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry, index) => {
        if (entry.isIntersecting) {
          setTimeout(() => {
            entry.target.classList.add('revealed');
          }, index * 100); // Délai progressif
        }
      });
    }, observerOptions);

    // Observer pour les groupes d'éléments en cascade
    const staggerObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
        }
      });
    }, staggerObserverOptions);

    // Observer tous les éléments avec animations de scroll
    const elementsToReveal = document.querySelectorAll('.scroll-reveal, .scroll-reveal-left, .scroll-reveal-right, .scroll-reveal-scale');
    const staggerElements = document.querySelectorAll('.stagger-reveal');
    
    elementsToReveal.forEach(el => observer.observe(el));
    staggerElements.forEach(el => staggerObserver.observe(el));

    // Cleanup
    return () => {
      observer.disconnect();
      staggerObserver.disconnect();
    };
  }, [activeTab]);

  // Effet pour les animations continues
  useEffect(() => {
    // Animation de données en temps réel pour le dashboard
    const dataFlowInterval = setInterval(() => {
      const dataFlowElements = document.querySelectorAll('.data-flow');
      dataFlowElements.forEach(el => {
        el.style.animation = 'none';
        setTimeout(() => {
          el.style.animation = 'dataFlow 3s linear infinite';
        }, Math.random() * 2000);
      });
    }, 5000);

    return () => clearInterval(dataFlowInterval);
  }, [activeTab]);

  // Fonction pour créer des éléments flottants
  const createFloatingElements = () => {
    return Array.from({ length: 3 }, (_, i) => (
      <div
        key={i}
        className="floating-element"
        style={{
          position: 'absolute',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: `linear-gradient(45deg, var(--accent-color), var(--success-color))`,
          top: `${20 + i * 30}%`,
          left: `${10 + i * 20}%`,
          animationDelay: `${i * 2}s`,
          opacity: 0.6,
          zIndex: -1
        }}
      />
    ));
  };

  // Actions optimisées avec traitement en arrière-plan
  const scrapeArticlesNow = async () => {
    if (backgroundTasks.scraping) return;
    
    setBackgroundTasks(prev => ({ ...prev, scraping: true }));
    
    try {
      // Démarrer le scraping en arrière-plan
      const response = await apiCall(`${BACKEND_URL}/api/articles/scrape-now`, { method: 'POST' });
      
      if (response.success) {
        alert(`✅ ${response.message}`);
        
        // Vérifier le statut périodiquement
        const checkStatus = async () => {
          try {
            const statusData = await apiCall(`${BACKEND_URL}/api/articles/scrape-status`);
            if (statusData.success && statusData.result) {
              const result = statusData.result;
              if (result.success !== undefined) {
                // Scraping terminé
                setBackgroundTasks(prev => ({ ...prev, scraping: false }));
                if (result.success) {
                  alert(`🎉 Scraping terminé ! ${result.total_articles} articles récupérés`);
                  loadTabData('articles', null, true);
                  loadDashboardStats();
                } else {
                  alert(`⚠️ Scraping terminé avec erreurs: ${result.error}`);
                }
                return;
              }
            }
            // Continuer à vérifier
            setTimeout(checkStatus, 10000); // Vérifier toutes les 10 secondes
          } catch (error) {
            console.error('Erreur vérification statut scraping:', error);
            setBackgroundTasks(prev => ({ ...prev, scraping: false }));
          }
        };
        
        setTimeout(checkStatus, 10000); // Première vérification après 10s
      }
    } catch (error) {
      alert(`❌ Erreur scraping: ${error.message}`);
      setBackgroundTasks(prev => ({ ...prev, scraping: false }));
    }
  };

  const captureRadioNow = async () => {
  if (backgroundTasks.capturing) return;
  
  setBackgroundTasks(prev => ({ ...prev, capturing: true }));
  
  try {
    // Par défaut on lance RCI (tu pourras ajouter un sélecteur)
    const res = await apiCall(`${BACKEND_URL}/api/transcriptions/capture-now?section=rci`, { method: 'POST' });
    if (res.success) {
      alert(`✅ ${res.message}`);
      // rafraîchis vite le statut puis recharges sections/statuts plus tard
      setTimeout(() => {
        loadTranscriptionStatus();
      }, 1000);
      setTimeout(() => {
        loadTranscriptionSections();
        loadTranscriptionStatus();
      }, 180000); // 3 minutes
    } else {
      alert(`❌ Erreur: ${res.error || 'Erreur inconnue'}`);
    }
  } catch (error) {
    alert(`❌ Erreur capture: ${error.message}`);
  } finally {
    setBackgroundTasks(prev => ({ ...prev, capturing: false }));
  }
};

  // Charger les transcriptions par sections
  const loadTranscriptionSections = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/sections`);
      const data = await response.json();
      if (data.success) {
        setTranscriptionSections(data.sections);
      }
    } catch (error) {
      console.error('Erreur chargement sections transcriptions:', error);
    }
  };

  // Charger le statut des transcriptions
  const loadTranscriptionStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/status`);
      const data = await response.json();
      if (data.success) {
        setTranscriptionStatus(data.status);
      }
    } catch (error) {
      console.error('Erreur chargement statut transcriptions:', error);
    }
  };

  // Lancer la capture d'une section spécifique
  const captureSection = async (section) => {
    try {
      setLoading(true);
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/capture-now?section=${section}`, {
        method: 'POST'
      });
      const data = await response.json();
      if (data.success) {
        alert(`✅ ${data.message}`);
        // Actualiser le statut immédiatement
        setTimeout(() => {
          loadTranscriptionStatus();
        }, 1000);
        
        // Actualiser les sections après le temps estimé de completion (3-5 min)
        setTimeout(() => {
          loadTranscriptionSections();
          loadTranscriptionStatus();
        }, 180000); // 3 minutes
      } else {
        alert(`❌ Erreur: ${data.error || 'Erreur inconnue'}`);
      }
    } catch (error) {
      console.error('Erreur capture section:', error);
      alert('❌ Erreur lors du lancement de la capture');
    } finally {
      setLoading(false);
    }
  };

  const createDigestNow = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/digest/create-now`, { method: 'POST' });
      if (response.success) {
        alert('✅ Digest créé avec succès !');
        loadTabData('digest', null, true);
        loadDashboardStats();
      }
    } catch (error) {
      alert(`❌ Erreur création digest: ${error.message}`);
    }
    setLoading(false);
  };

  const runSchedulerJob = async (jobId) => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/scheduler/run-job/${jobId}`, { method: 'POST' });
      if (response.success) {
        alert(`✅ Job ${jobId} exécuté avec succès !`);
        loadTabData('scheduler');
        loadDashboardStats();
      } else {
        alert(`❌ Erreur job ${jobId}: ${response.message}`);
      }
    } catch (error) {
      alert(`❌ Erreur exécution job: ${error.message}`);
    }
    setLoading(false);
  };

  const uploadAudio = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${BACKEND_URL}/api/transcribe`, {
        method: 'POST',
        body: formData
      });
      
      const data = await response.json();
      if (data.success) {
        alert('✅ Transcription réussie !');
        loadTabData('transcription', null, true);
        loadDashboardStats();
      } else {
        throw new Error(data.detail || 'Erreur transcription');
      }
    } catch (error) {
      alert(`❌ Erreur transcription: ${error.message}`);
    }
    setLoading(false);
  };

  const invalidateCache = async () => {
    try {
      await apiCall(`${BACKEND_URL}/api/cache/invalidate`, { method: 'POST' });
      alert('✅ Cache vidé avec succès !');
      // Recharger les données
      loadDashboardStats();
      if (activeTab !== 'dashboard') {
        loadTabData(activeTab, null, true);
      }
    } catch (error) {
      alert(`❌ Erreur vidage cache: ${error.message}`);
    }
  };

  // Recherche automatique des sujets prioritaires au démarrage
  const performAutoSearch = async () => {
    if (autoSearchCompleted) return;
    
    const prioritySubjects = ['cd971', 'Guy Losbar', 'département guadeloupe', 'GUSR', 'Ary Chalus'];
    const results = {};
    
    console.log('🔍 Démarrage de la recherche automatique des sujets prioritaires...');
    
    for (const subject of prioritySubjects) {
      try {
        console.log(`Recherche automatique: ${subject}`);
        const response = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(subject)}`);
        if (response.success) {
          results[subject] = {
            total_results: response.total_results,
            articles_count: response.articles ? response.articles.length : 0,
            social_posts_count: response.social_posts ? response.social_posts.length : 0
          };
        }
        // Petit délai entre les recherches pour éviter la surcharge
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (error) {
        console.warn(`Erreur recherche automatique pour "${subject}":`, error.message);
        results[subject] = { error: error.message };
      }
    }
    
    setAutoSearchResults(results);
    setAutoSearchCompleted(true);
    console.log('✅ Recherche automatique terminée:', results);
  };

  // Fonction de recherche sociale spécifique
  const handleSocialSearch = async (query) => {
    if (!query || query.trim().length < 2) {
      setSocialSearchError('Veuillez saisir au moins 2 caractères');
      return;
    }
    
    setSocialSearchLoading(true);
    setSocialSearchError(null);
    
    try {
      console.log(`🔍 Recherche sociale pour: "${query}"`);
      
      // Lancer le scraping pour ce sujet spécifique
      const scrapingResponse = await apiCall(`${BACKEND_URL}/api/social/scrape-keyword`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: query })
      });
      
      if (scrapingResponse.success) {
        // Attendre un peu pour que le scraping se termine
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // Rechercher les résultats
        const searchResponse = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(query)}&social_only=true`);
        
        if (searchResponse.success) {
          setSocialSearchResults({
            query: query,
            social_posts: searchResponse.social_posts || [],
            total_results: searchResponse.total_results || 0,
            scraped_at: new Date().toISOString()
          });
        } else {
          setSocialSearchError(searchResponse.error || 'Erreur lors de la recherche');
        }
      } else {
        setSocialSearchError(scrapingResponse.error || 'Erreur lors du scraping');
      }
    } catch (error) {
      console.error('Erreur recherche sociale:', error);
      setSocialSearchError(`Erreur: ${error.message}`);
    } finally {
      setSocialSearchLoading(false);
    }
  };

  // Fonction de recherche
  const handleSearch = async (query) => {
    if (!query || query.trim().length < 2) {
      setSearchResults(null);
      return;
    }

    setSearchLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(query.trim())}`);
      if (response.success) {
        setSearchResults(response);
      } else {
        setError(`Erreur de recherche: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur de recherche: ${error.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  // Charger les suggestions de recherche
  const loadSearchSuggestions = async (query = '') => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/search/suggestions?q=${encodeURIComponent(query)}`);
      if (response.success) {
        setSearchSuggestions(response.suggestions);
      }
    } catch (error) {
      console.warn('Erreur suggestions:', error.message);
    }
  };

  // Charger les commentaires (posts des réseaux sociaux)
  const loadComments = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/comments`);
      if (response.success) {
        setComments(response.comments);
      } else {
        setError(`Erreur commentaires: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur commentaires: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Analyser les commentaires par entité
  const analyzeComments = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/comments/analyze`, { method: 'POST' });
      if (response.success) {
        setCommentsAnalysis(response.analysis);
      } else {
        setError(`Erreur analyse commentaires: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur analyse commentaires: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Analyser le sentiment d'un texte
  const analyzeSentiment = async (useAsync = false) => {
    if (!sentimentText.trim()) {
      setError('Veuillez entrer un texte à analyser');
      return;
    }

    setSentimentLoading(true);
    setSentimentResult(null);
    setError(null);

    try {
      const response = await apiCall(`${BACKEND_URL}/api/sentiment/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          text: sentimentText.trim(),
          async: useAsync 
        })
      });

      if (response.success) {
        if (response.async) {
          // Mode asynchrone - polling du statut
          setSentimentResult({ 
            mode: 'async', 
            status: 'processing', 
            hash: response.text_hash,
            message: response.message 
          });
          pollSentimentStatus(response.text_hash);
        } else {
          // Mode synchrone ou cache hit
          setSentimentResult(response);
        }
      } else {
        setError(`Erreur analyse sentiment: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur analyse sentiment: ${error.message}`);
    } finally {
      setSentimentLoading(false);
    }
  };

  // Polling du statut pour l'analyse asynchrone
  const pollSentimentStatus = async (textHash) => {
    let attempts = 0;
    const maxAttempts = 15;

    const poll = async () => {
      attempts++;
      try {
        const response = await apiCall(`${BACKEND_URL}/api/sentiment/status/${textHash}`);
        
        if (response.success && response.status === 'completed') {
          setSentimentResult(response);
          setSentimentLoading(false);
        } else if (response.status === 'not_found') {
          // Réessayer l'analyse (probablement en cache maintenant)
          analyzeSentiment(true);
        } else if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        } else {
          setError('Timeout: analyse plus longue que prévue');
          setSentimentLoading(false);
        }
      } catch (error) {
        setError(`Erreur vérification statut: ${error.message}`);
        setSentimentLoading(false);
      }
    };

    setTimeout(poll, 2000);
  };

  // Prédire la réaction de la population
  const predictReaction = async () => {
    if (!sentimentText.trim()) {
      setError('Veuillez entrer un texte pour la prédiction');
      return;
    }

    setPredictionLoading(true);
    // Ne jamais remettre l'état à null pour éviter les accès undefined dans le rendu
    setError(null);

    try {
      const response = await apiCall(`${BACKEND_URL}/api/sentiment/predict-reaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: sentimentText.trim(),
          context: { source: 'frontend_test' }
        })
      });

      if (response?.success) {
        // Normalise toujours la réponse pour garantir la présence des champs
        const normalized = normalizeReactionResponse(response);
        setReactionPrediction(normalized);
      } else {
        // En cas d'erreur API, garder un objet sûr avec valeurs par défaut
        setReactionPrediction(DEFAULT_REACTION);
        setError(`Erreur prédiction réaction: ${response?.error || 'Réponse invalide'}`);
      }
    } catch (error) {
      // En cas d'exception réseau/JSON, garder un objet sûr
      setReactionPrediction(DEFAULT_REACTION);
      setError(`Erreur prédiction réaction: ${error.message}`);
    } finally {
      setPredictionLoading(false);
    }
  };

  // Utiliser un exemple de texte
  const useSentimentExample = (example) => {
    setSentimentText(example);
    setSentimentResult(null);
    setReactionPrediction(null);
  };

  // Charger les sources disponibles pour les filtres
  const loadAvailableSources = async () => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/articles/sources`);
      if (response.success) {
        setAvailableSources(response.sources);
      }
    } catch (error) {
      console.warn('Erreur chargement sources:', error.message);
    }
  };

  // Charger les articles filtrés
  const loadFilteredArticles = async (newFilters = null, offset = 0) => {
    const activeFilters = newFilters || filters;
    
    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: offset.toString(),
        sort_by: activeFilters.sortBy
      });
      
      if (activeFilters.dateStart) params.append('date_start', activeFilters.dateStart);
      if (activeFilters.dateEnd) params.append('date_end', activeFilters.dateEnd);
      if (activeFilters.source && activeFilters.source !== 'all') params.append('source', activeFilters.source);
      if (activeFilters.searchText) params.append('search_text', activeFilters.searchText);
      
      const response = await apiCall(`${BACKEND_URL}/api/articles/filtered?${params}`);
      if (response.success) {
        if (offset === 0) {
          setFilteredArticles(response.articles);
        } else {
          setFilteredArticles(prev => [...prev, ...response.articles]);
        }
                       const safePagination = {
          total: response.pagination?.total ?? 0,
          offset: response.pagination?.offset ?? 0,
          returned: response.pagination?.returned ?? (response.articles?.length ?? 0),
          hasMore: response.pagination?.hasMore ?? false
        };
        setPagination(safePagination);
      }
    } catch (error) {
      setError(`Erreur filtrage articles: ${error.message}`);
    }
  };

  // Charger les données d'analytics
  const loadAnalyticsData = async () => {
    try {
      setLoading(true);
      
      // Charger toutes les analytics en parallèle
      const [sourceData, timelineData, sentimentData, metricsData] = await Promise.all([
        apiCall(`${BACKEND_URL}/api/analytics/articles-by-source`),
        apiCall(`${BACKEND_URL}/api/analytics/articles-timeline`),
        apiCall(`${BACKEND_URL}/api/analytics/sentiment-by-source`),
        apiCall(`${BACKEND_URL}/api/analytics/dashboard-metrics`)
      ]);
      
      setAnalyticsData({
        sourceChart: sourceData?.success ? normalizeAnalytics(sourceData) : EMPTY_ANALYTICS,
        timelineChart: timelineData?.success ? normalizeAnalytics(timelineData) : EMPTY_ANALYTICS,
        sentimentChart: sentimentData?.success ? normalizeAnalytics(sentimentData) : EMPTY_ANALYTICS,
        dashboardMetrics: metricsData?.success ? (metricsData.data || metricsData.metrics || metricsData) : {}
      });
      
    } catch (error) {
      console.warn('Erreur chargement analytics:', error.message);
    } finally {
      setLoading(false);
    }
  };

  // Appliquer les filtres
  const applyFilters = (newFilters) => {
    setFilters(newFilters);
    loadFilteredArticles(newFilters, 0);
  };

  // Réinitialiser les filtres
  const resetFilters = () => {
    const defaultFilters = {
      dateStart: '',
      dateEnd: '',
      source: 'all',
      searchText: '',
      sortBy: 'date_desc'
    };
    setFilters(defaultFilters);
    loadFilteredArticles(defaultFilters, 0);
  };

  // Charger plus d'articles (pagination)
  const loadMoreArticles = () => {
              if (pagination?.hasMore && !loading) {
      const nextOffset = (pagination?.offset ?? 0) + (pagination?.returned ?? 0);
      loadFilteredArticles(filters, nextOffset);
    }
  };

  // Charger les stats des réseaux sociaux
  const loadSocialStats = async () => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/social/stats`);
      if (response.success) {
        setSocialStats(response.stats);
      }
    } catch (error) {
      console.warn('Erreur stats réseaux sociaux:', error.message);
    }
  };

  // Lancer le scraping des réseaux sociaux
  const startSocialScraping = async () => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/social/scrape-now`, { method: 'POST' });
      if (response.success) {
        setBackgroundTasks(prev => ({
          ...prev,
          socialScraping: { status: 'running', message: response.message }
        }));
        // Recharger les stats après quelques secondes
        setTimeout(() => {
          loadSocialStats();
          loadComments();
        }, 30000);
      } else {
        setError(`Erreur scraping social: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur scraping social: ${error.message}`);
    }
  };

  return (
    <div className="app">
      <GlobalStyles />
      {/* Header style Apple moderne avec animations */}
      <header className="glass-header animate-slide-in-top">
        <div className="header-content">
          <div className="header-left">
            {/* Menu hamburger mobile */}
            <button 
              className="mobile-menu-button micro-bounce"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Menu"
            >
              <div className={`hamburger-icon ${mobileMenuOpen ? 'open' : ''}`}>
                <span></span>
                <span></span>
                <span></span>
              </div>
            </button>
            
            <AppLogo size={48} />
            <div className="header-title-section">
              <p className="app-subtitle">Intelligence artificielle • Surveillance médiatique • Guadeloupe</p>
            </div>
          </div>
          <div className="header-right">
            <span className="header-last-update animate-fade-in-right animate-delay-300">
              Dernière MAJ: {new Date().toLocaleDateString('fr-FR', { 
                day: 'numeric', 
                month: 'short', 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </span>
          </div>
        </div>
      </header>

      {/* Overlay mobile */}
      <div 
        className={`mobile-overlay ${mobileMenuOpen ? 'active' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
      ></div>

      {/* Barre de statut des tâches - Style Apple moderne */}
      {(backgroundTasks.scraping || backgroundTasks.capturing) && (
        <div className="content-section">
          <div className="glass-card animate-slide-in" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
            <div className="flex items-center gap-6">
              {backgroundTasks.scraping && (
                <div className="flex items-center gap-3">
                  <div className="animate-pulse">
                    <div style={{ 
                      width: '8px', 
                      height: '8px', 
                      background: '#3b82f6', 
                      borderRadius: '50%',
                      boxShadow: '0 0 20px rgba(59, 130, 246, 0.6)'
                    }}></div>
                  </div>
                  <span className="status-indicator status-info">
                    🔄 Scraping en cours... (2-3 min)
                  </span>
                </div>
              )}
              {backgroundTasks.capturing && (
                <div className="flex items-center gap-3">
                  <div className="animate-pulse">
                    <div style={{ 
                      width: '8px', 
                      height: '8px', 
                      background: '#f59e0b', 
                      borderRadius: '50%',
                      boxShadow: '0 0 20px rgba(245, 158, 11, 0.6)'
                    }}></div>
                  </div>
                  <span className="status-indicator status-warning">
                    📻 Capture radio en cours... (3-5 min)
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation style Apple moderne avec support mobile et animations */}
      <div className="content-section">
        <nav className={`tab-navigation ${mobileMenuOpen ? 'mobile-open' : ''} animate-fade-in-up animate-delay-200`}>
          {[
            { id: 'dashboard', name: 'Dashboard', icon: 'dashboard' },
            { id: 'search', name: 'Recherche', icon: 'search' },
            { id: 'articles', name: 'Articles', icon: 'articles' },
            { id: 'analytics', name: 'Analytics', icon: 'analytics' },
            { id: 'sentiment', name: 'Analyse Sentiment', icon: 'sentiment' },
            { id: 'comments', name: 'Réseaux Sociaux', icon: 'social' },
            { id: 'transcription', name: 'Radio', icon: 'radio' },
            { id: 'digest', name: 'Digest', icon: 'digest' }
          ].map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''} micro-bounce animate-fade-in-left`}
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content style Apple moderne */}
      <main className="content-section">
        {/* Affichage des erreurs - Style Apple */}
        {error && (
          <div className="glass-card animate-slide-in" style={{ 
            padding: '1rem', 
            marginBottom: '2rem',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="status-indicator status-error">{error}</span>
              <button 
                onClick={() => setError(null)} 
                className="btn-secondary"
                style={{ padding: '0.5rem', minWidth: 'auto' }}
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Loading overlay animé - Style Apple */}
        {loading && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(13, 17, 23, 0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999
          }} className="animate-fade-in-scale">
            <div className="glass-card animate-bounce-in" style={{ padding: '2rem', textAlign: 'center' }}>
              <div className="loading-spinner" style={{ 
                width: '40px', 
                height: '40px', 
                background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', 
                borderRadius: '50%',
                margin: '0 auto 1rem',
                border: '4px solid rgba(59, 130, 246, 0.3)',
                borderTop: '4px solid #3b82f6'
              }}></div>
              <p style={{ color: '#e2e8f0' }} className="animate-pulse">Traitement en cours...</p>
            </div>
          </div>
        )}

        {/* Dashboard Narratif avec animations continues */}
        {activeTab === 'dashboard' && (
          <div className="narrative-section dashboard-container">
            {createFloatingElements()}
            
            {/* Header Story */}
            <div className="story-header scroll-reveal">
              <h1 className="story-title">
                🏝️ Veille Média Guadeloupe
              </h1>
              <p className="story-subtitle">
                Découvrez l'actualité guadeloupéenne à travers une surveillance intelligente des médias locaux.
                Suivez le pouls de votre territoire en temps réel.
              </p>
            </div>
{/* Stats narratives */}
{Object.keys(dashboardStats || {}).length > 0 && (
  <div
    className=""
    style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
      gap: '2rem',
      marginBottom: '4rem'
    }}
  >
    <div className="stat-card-narrative">
                    <div className="stat-value">{dashboardStats.articles_today || dashboardStats.total_articles || 0}</div>
                    <div className="stat-label">Articles du Jour</div>
                    <div className="stat-sublabel">Actualités fraîches</div>
                  </div>
                  
                  <div className="stat-card-narrative">
                    <div className="stat-value">{dashboardStats.total_articles || 0}</div>
                    <div className="stat-label">Total Articles</div>
                    <div className="stat-sublabel">Base de données</div>
                  </div>
                  
                  <div className="stat-card-narrative">
                    <div className="stat-value">{dashboardStats.active_sources || 4}</div>
                    <div className="stat-label">Sources Actives</div>
                    <div className="stat-sublabel">Médias surveillés</div>
                  </div>
                  
      <div className="stat-card-narrative">
        <div className="stat-value">{dashboardStats.transcriptions_today || dashboardStats.total_transcriptions || 0}</div>
        <div className="stat-label">Transcriptions</div>
        <div className="stat-sublabel">Contenus audio</div>
      </div>
  </div>
)}

            {/* Résultats de recherche automatique avec logos */}
            {autoSearchCompleted && Object.keys(autoSearchResults).length > 0 && (
              <div className="" style={{ marginBottom: '4rem' }}>
                <div className="content-block">
                  <div className="content-block-header">
                    <h3 className="content-block-title">🎯 Surveillance Prioritaire</h3>
                    <span className="filter-badge">Automatique</span>
                  </div>
                  <div className="" style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', 
                    gap: '1.5rem' 
                  }}>
                    {Object.entries(autoSearchResults).map(([subject, result], index) => (
                      <div
                        key={subject}
                        className="article-card-narrative"
                        style={{ animationDelay: `${index * 0.1}s` }}
                      >
                        <h4 className="font-semibold mb-2" style={{ color: '#2c3e50', fontSize: '1.1rem' }}>
                          {subject}
                        </h4>
                        {result.error ? (
                          <p className="text-sm" style={{ color: '#e74c3c' }}>Erreur de surveillance</p>
                        ) : (
                          <div className="text-sm" style={{ color: '#34495e' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                              <span>📰</span>
                              <span>{result.articles_count || 0} articles</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                              <span>💬</span>
                              <span>{result.social_posts_count || 0} posts sociaux</span>
                            </div>
                            <div className="font-medium" style={{ color: '#2c3e50', fontSize: '1rem' }}>
                              Total: {result.total_results || 0} mentions
                            </div>
                          </div>
                        )}
                        <button
                          onClick={() => {
                            setSearchQuery(subject);
                            handleSearch(subject);
                            setActiveTab('search');
                          }}
                          className="glass-button primary pulse-glow"
                          style={{ 
                            marginTop: '1rem', 
                            padding: '0.5rem 1rem', 
                            fontSize: '0.85rem',
                            width: '100%'
                          }}
                        >
                          🔍 Explorer
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Barre de recherche narrative */}
            <div className="scroll-reveal-right">
              <div className="content-block" style={{ 
                background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(16, 185, 129, 0.1) 100%)',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                position: 'relative',
                overflow: 'hidden'
              }}>
                <div className="background-pulse" style={{ 
                  position: 'absolute', 
                  top: 0, 
                  left: 0, 
                  right: 0, 
                  bottom: 0, 
                  zIndex: -1 
                }} />
                <h3 className="text-xl font-bold mb-4" style={{ color: '#2c3e50' }}>
                  🔍 Recherche Intelligente
                </h3>
                <div className="flex gap-4 flex-col md:flex-row">
                  <div className="flex-1">
                    <div className="relative">
                      <input
                        type="text"
                        placeholder="Rechercher Guy Losbar, CD971, actualités..."
                        value={searchQuery}
                        onChange={(e) => {
                          setSearchQuery(e.target.value);
                          if (e.target.value.length >= 2) {
                            loadSearchSuggestions(e.target.value);
                          }
                        }}
                        onKeyPress={(e) => {
                          if (e.key === 'Enter') {
                            handleSearch(searchQuery);
                            setActiveTab('search');
                          }
                        }}
                        className="glass-input pl-12"
                        style={{ fontSize: '1.1rem', padding: '1rem 1rem 1rem 3rem' }}
                      />
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                        <svg className="w-6 h-6 text-blue-500 floating-element" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                        </svg>
                      </div>
                      
                      {/* Suggestions améliorées */}
                      {searchSuggestions.length > 0 && searchQuery.length >= 2 && (
                        <div className="absolute top-full left-0 w-full mt-2 content-block z-50" style={{ 
                          boxShadow: '0 25px 50px rgba(0,0,0,0.15)',
                          borderRadius: 'var(--radius-xl)'
                        }}>
                          {searchSuggestions.map((suggestion, index) => (
                            <button
                              key={index}
                              onClick={() => {
                                setSearchQuery(suggestion);
                                handleSearch(suggestion);
                                setActiveTab('search');
                                setSearchSuggestions([]);
                              }}
                              className="w-full text-left px-4 py-3 hover:bg-blue-50 transition-all duration-200 first:rounded-t-xl last:rounded-b-xl"
                              style={{ color: '#2c3e50', borderBottom: index < searchSuggestions.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}
                            >
                              <span className="mr-2">🔍</span>
                              {suggestion}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      handleSearch(searchQuery);
                      setActiveTab('search');
                    }}
                    disabled={searchLoading}
                    className="glass-button primary"
                    style={{ padding: '1rem 2rem', fontSize: '1.1rem' }}
                  >
                    {searchLoading ? (
                      <span className="animate-rotate">⏳</span>
                    ) : (
                      <span className="floating-element">🚀</span>
                    )} 
                    Rechercher
                  </button>
                </div>
                
                {/* Suggestions populaires avec animations */}
                <div className="mt-6">
                  <p className="text-sm mb-3" style={{ color: '#7f8c8d', fontWeight: '600' }}>
                    Sujets populaires :
                  </p>
                  <div className="stagger-reveal">
                    <div className="flex flex-wrap gap-2">
                      {['cd971', 'Guy Losbar', 'département guadeloupe', 'GUSR', 'Ary Chalus', 'Budget départemental', 'Environnement', 'Tourisme'].map((term, index) => (
                        <button
                          key={term}
                          onClick={() => {
                            setSearchQuery(term);
                            handleSearch(term);
                            setActiveTab('search');
                          }}
                          className="glass-button secondary floating-element"
                          style={{ 
                            padding: '0.6rem 1.2rem', 
                            fontSize: '0.9rem',
                            animationDelay: `${index * 0.5}s`
                          }}
                        >
                          {term}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Actions automatiques avec animations */}
            <div className="scroll-reveal" style={{ marginTop: '4rem' }}>
              <div className="content-block">
                <h3 className="text-xl font-bold mb-4" style={{ color: '#2c3e50' }}>
                  🚀 Actions Automatiques
                </h3>
                <div className="stagger-reveal" style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', 
                  gap: '1.5rem' 
                }}>
                  <button
                    onClick={scrapeArticlesNow}
                    disabled={backgroundTasks.scraping}
                    className={`stat-card-narrative`}
                    style={{ cursor: 'pointer', border: backgroundTasks.scraping ? '2px solid var(--accent-color)' : '1px solid var(--border-color)' }}
                  >
                    <div className="stat-value" style={{ fontSize: '2rem', marginBottom: '1rem' }}>
                      {backgroundTasks.scraping ? (
                        <span className="animate-rotate">⏳</span>
                      ) : (
                        <span className="floating-element">📰</span>
                      )}
                    </div>
                    <div className="stat-label">
                      {backgroundTasks.scraping ? 'Scraping en cours...' : 'Scraper Articles'}
                    </div>
                    <div className="stat-sublabel">Récupérer les dernières actualités</div>
                  </button>
                  
                  <button
                    onClick={captureRadioNow}
                    disabled={backgroundTasks.capturing}
                    className={`stat-card-narrative`}
                    style={{ cursor: 'pointer', border: backgroundTasks.capturing ? '2px solid var(--success-color)' : '1px solid var(--border-color)' }}
                  >
                    <div className="stat-value" style={{ fontSize: '2rem', marginBottom: '1rem' }}>
                      {backgroundTasks.capturing ? (
                        <span className="animate-rotate">⏳</span>
                      ) : (
                        <span className="floating-element">📻</span>
                      )}
                    </div>
                    <div className="stat-label">
                      {backgroundTasks.capturing ? 'Capture en cours...' : 'Capturer Radio'}
                    </div>
                    <div className="stat-sublabel">Enregistrer les émissions</div>
                  </button>
                  
                  <button
                    onClick={createDigestNow}
                    className="stat-card-narrative"
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="stat-value" style={{ fontSize: '2rem', marginBottom: '1rem' }}>
                      <span className="floating-element">📄</span>
                    </div>
                    <div className="stat-label">Créer Digest</div>
                    <div className="stat-sublabel">Résumé quotidien intelligent</div>
                  </button>
                  
                  <label className="stat-card-narrative cursor-pointer" style={{ cursor: 'pointer' }}>
                    <div className="stat-value" style={{ fontSize: '2rem', marginBottom: '1rem' }}>
                      <span className="floating-element">🎤</span>
                    </div>
                    <div className="stat-label">Upload Audio</div>
                    <div className="stat-sublabel">Analyser un fichier audio</div>
                    <input type="file" accept="audio/*" onChange={uploadAudio} className="hidden" />
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Articles */}
        {activeTab === 'articles' && (
          <div className="animate-slide-in">
            <div className="section-header">
              <h2 className="section-title">📰 Articles de Guadeloupe</h2>
              <p className="section-subtitle">Sources : France-Antilles, RCI.fm, La 1ère, KaribInfo</p>
            </div>

            <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                  <strong>Programmé :</strong> Tous les jours à 10H00 | <strong>Cache :</strong> 5 minutes
                </div>
                <button
                  onClick={scrapeArticlesNow}
                  disabled={backgroundTasks.scraping}
                  className={backgroundTasks.scraping ? 'btn-secondary' : 'btn-primary'}
                  style={{ opacity: backgroundTasks.scraping ? 0.6 : 1 }}
                >
                  {backgroundTasks.scraping ? '⏳ Scraping...' : '🔄 Scraper Maintenant'}
                </button>
              </div>
            </div>

            <div className="article-list">
              {filteredArticles.map(article => (
                <article key={article.id} className="article-card-narrative">
                  {/* Header avec logo et titre narratif */}
                  <header className="article-header-narrative">
                    <SourceLogo source={article.source} size={48} className="source-logo-narrative" />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3 className="article-title" style={{ 
                        margin: 0, 
                        lineHeight: '1.4',
                        fontSize: '1.1rem',
                        fontWeight: '600'
                      }}>
                        <a href={article.url} target="_blank" rel="noopener noreferrer" style={{ 
                          textDecoration: 'none', 
                          color: 'inherit', 
                          display: 'block',
                          transition: 'color 0.3s ease'
                        }}>
                          {article.title}
                        </a>
                      </h3>
                    </div>
                  </header>
                  
                  {/* Résumé de l'article avec style narratif */}
                  <div className="article-explication" style={{
                    fontSize: '0.95rem',
                    lineHeight: '1.6',
                    color: 'var(--text-secondary)',
                    marginBottom: '1rem'
                  }}>
                    {article.summary || article.ai_summary || "Résumé non disponible"}
                  </div>

                  {/* Métadonnées avec logos et animations */}
                  <footer className="article-meta" style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    flexWrap: 'wrap',
                    marginBottom: '1rem'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span className="article-source" style={{
                        background: getSiteLogo(article.source).bg,
                        color: getSiteLogo(article.source).color,
                        padding: '0.375rem 0.75rem',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '0.8rem',
                        fontWeight: '600',
                        border: `1px solid ${getSiteLogo(article.source).borderColor}`
                      }}>
                        {article.source}
                      </span>
                      <span className="article-date" style={{
                        color: 'var(--text-muted)',
                        fontSize: '0.8rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.25rem'
                      }}>
                        <span className="" style={{ fontSize: '0.7rem' }}>🕒</span>
                        {new Date(article.published_at || article.scraped_at).toLocaleDateString('fr-FR', {
                          day: 'numeric',
                          month: 'short',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </span>
                    </div>
                    {article.sentiment_score && (
                      <span className={`article-sentiment ${
                        article.sentiment_score > 0.1 
                          ? 'positive' 
                          : article.sentiment_score < -0.1 
                            ? 'negative' 
                            : 'neutral'
                      }`} style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontWeight: '500'
                      }}>
                        {article.sentiment_score > 0.1 ? '😊 Positif' : article.sentiment_score < -0.1 ? '😞 Négatif' : '😐 Neutre'}
                      </span>
                    )}
                  </footer>

                  {/* Actions sur l'article avec style narratif */}
                  <div className="article-actions" style={{
                    display: 'flex',
                    gap: '0.75rem',
                    flexWrap: 'wrap'
                  }}>
                    <a 
                      href={article.url} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="glass-button primary"
                      style={{ 
                        fontSize: '0.85rem',
                        padding: '0.5rem 1rem'
                      }}
                    >
                      <span className="">📖</span>
                      Lire l'article
                    </a>
                    {article.ai_summary && (
                      <button 
                        className="glass-button secondary"
                        style={{ 
                          fontSize: '0.85rem',
                          padding: '0.5rem 1rem'
                        }}
                      >
                        <span className="">🤖</span>
                        Résumé IA
                      </button>
                    )}
                  </div>
                </article>
              ))}
              
              {articles.length === 0 && !loading && (
                <div className="articles-empty-state">
                  <div className="articles-empty-icon">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14,2 14,8 20,8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                      <polyline points="10,9 9,9 8,9"/>
                    </svg>
                  </div>
                  <h3 className="articles-empty-title">Aucun article disponible</h3>
                  <p className="articles-empty-description">
                    Lancez un scraping pour récupérer les derniers articles de Guadeloupe
                  </p>
                </div>
              )}

              {loading && articles.length === 0 && (
                <>
                  {[...Array(3)].map((_, index) => (
                    <div key={index} className="article-skeleton">
                      <div className="skeleton-line title"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line meta"></div>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )}

        {/* Articles avec filtres avancés et animations */}
        {activeTab === 'articles' && (
          <div className="animate-fade-in-up">
            {/* Header avec filtres */}
            <div className="section-container">
              <div className="section-header animate-fade-in-scale">
                <h2 className="section-title animate-wave">📰 Articles de Presse</h2>
                <p className="section-subtitle animate-fade-in-up animate-delay-200">Filtrage et tri avancés des articles locaux</p>
              </div>

              {/* Interface de filtres avec animations */}
              <div className="glass-card animate-fade-in-up animate-delay-300" style={{ padding: '2rem', marginBottom: '2rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }} className="stagger-children">
                  {/* Filtre par texte */}
                  <div className="filter-field animate-fade-in-left">
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500', color: '#374151' }}>
                      Recherche
                    </label>
                    <input
                      type="text"
                      placeholder="Titre, source..."
                      value={filters.searchText}
                      onChange={(e) => setFilters({...filters, searchText: e.target.value})}
                      className="glass-input"
                    />
                  </div>

                  {/* Filtre par source */}
                  <div className="filter-field animate-fade-in-left animate-delay-100">
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500', color: '#374151' }}>
                      Source
                    </label>
                    <select
  value={filters.sortBy}
  onChange={(e) => setFilters({ ...filters, sortBy: e.target.value })}
  className="glass-input"
>
  <option value="date">Date</option>
  <option value="source">Source</option>
  <option value="sentiment">Sentiment</option>
</select>
                  </div>

                  {/* Date de début */}
                  <div className="filter-field animate-fade-in-left animate-delay-200">
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500', color: '#374151' }}>
                      Date début
                    </label>
                    <input
                      type="date"
                      value={filters.dateStart}
                      onChange={(e) => setFilters({...filters, dateStart: e.target.value})}
                      className="glass-input"
                    />
                  </div>

                  {/* Date de fin */}
                  <div className="filter-field animate-fade-in-left animate-delay-300">
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500', color: '#374151' }}>
                      Date fin
                    </label>
                    <input
                      type="date"
                      value={filters.dateEnd}
                      onChange={(e) => setFilters({...filters, dateEnd: e.target.value})}
                      className="glass-input"
                    />
                  </div>

                  {/* Tri */}
                  <div className="filter-field animate-fade-in-left animate-delay-400">
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500', color: '#374151' }}>
                      Trier par
                    </label>
                    <select
                      value={filters.sortBy}
                      onChange={(e) => setFilters({...filters, sortBy: e.target.value})}
                      className="glass-input"
                    >
                      <option value="date_desc">Date ↓</option>
                      <option value="date_asc">Date ↑</option>
                      <option value="source_asc">Source A-Z</option>
                      <option value="source_desc">Source Z-A</option>
                      <option value="title_asc">Titre A-Z</option>
                      <option value="title_desc">Titre Z-A</option>
                    </select>
                  </div>
                </div>

                {/* Boutons d'action avec animations */}
                <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }} className="stagger-children">
                  <button
                    onClick={() => applyFilters(filters)}
                    className="glass-button primary micro-bounce animate-bounce-in"
                    disabled={loading}
                  >
                    {loading ? <span className="animate-rotate">⏳</span> : '🔍'} Appliquer les filtres
                  </button>
                  <button
                    onClick={resetFilters}
                    className="glass-button secondary micro-bounce animate-bounce-in animate-delay-100"
                  >
                    🔄 Réinitialiser
                  </button>
                </div>
              </div>

              {/* Résultats avec animations */}
              <div className="glass-card animate-fade-in-up animate-delay-600" style={{ padding: '1.5rem' }}>
                {/* Métadonnées des résultats */}
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  marginBottom: '1.5rem',
                  padding: '1rem',
                  background: 'rgba(59, 130, 246, 0.05)',
                  borderRadius: '8px',
                  border: '1px solid rgba(59, 130, 246, 0.1)'
                }} className="animate-slide-down">
                  <span style={{ fontWeight: '500', color: '#1e40af' }} className="animate-count-up">
                    {pagination.total} articles trouvés
                  </span>
                  <span style={{ color: '#6b7280', fontSize: '0.9rem' }} className="animate-fade-in-right">
                    Page {Math.floor(pagination.offset / 50) + 1}
                  </span>
                </div>

                {/* Liste des articles filtrés avec logos et animation en cascade */}
                <div className="articles-grid stagger-children">
                  {filteredArticles.map((article, index) => (
                    <div key={`${article.id || index}`} className="article-card animate-fade-in-scale" style={{ animationDelay: `${index * 0.05}s` }}>
                      <div className="article-content">
                        {/* Header avec logo */}
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'flex-start', 
                          gap: '0.75rem', 
                          marginBottom: '0.75rem' 
                        }}>
                          <SourceLogo source={article.source} size={40} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <h3 className="article-title" style={{ 
                              margin: 0, 
                              lineHeight: '1.4',
                              fontSize: '1rem' 
                            }}>
                              <a 
                                href={article.url} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                style={{ textDecoration: 'none', color: 'inherit' }}
                              >
                                {article.title}
                              </a>
                            </h3>
                          </div>
                        </div>
                        
                        {/* Metadata enrichie */}
                        <div className="article-meta" style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '0.5rem',
                          flexWrap: 'wrap'
                        }}>
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem'
                          }}>
                            <span className="article-source" style={{
                              background: getSiteLogo(article.source).bg,
                              color: getSiteLogo(article.source).color,
                              padding: '0.25rem 0.5rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.75rem',
                              fontWeight: '500'
                            }}>
                              {article.source}
                            </span>
                          </div>
                          <span className="article-date" style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.75rem'
                          }}>
                            {new Date(article.scraped_at).toLocaleDateString('fr-FR', {
                              day: 'numeric',
                              month: 'short',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Bouton charger plus avec animation */}
                {pagination.hasMore && (
                  <div style={{ textAlign: 'center', marginTop: '2rem' }}>
                    <button
                      onClick={loadMoreArticles}
                      className="glass-button secondary micro-bounce animate-bounce-in"
                      disabled={loading}
                    >
                      {loading ? <span className="animate-rotate">⏳</span> : '📄'} Charger plus d'articles
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Analytics et graphiques avec animations */}
        {activeTab === 'analytics' && (
          <div className="animate-fade-in-up">
            <div className="section-container">
              <div className="section-header animate-fade-in-scale">
                <h2 className="section-title animate-wave">📊 Analytics Visuels</h2>
                <p className="section-subtitle animate-fade-in-up animate-delay-200">Analyses graphiques et métriques avancées</p>
              </div>

              {/* Métriques du dashboard enrichies avec animations */}
              {analyticsData.dashboardMetrics && (
                <div className="stats-container stagger-children" style={{ marginBottom: '3rem' }}>
                  {Object.entries(analyticsData.dashboardMetrics.metrics).map(([key, metric], index) => (
                    <div 
                      key={key} 
                      className="stat-card enhanced animate-bounce-in" 
                      style={{ animationDelay: `${index * 0.1}s` }}
                    >
                      <div className="stat-label">{metric.label}</div>
                      <div className="stat-value animate-count-up">
                        {metric.value}
                        {metric.evolution_pct && (
                          <span style={{ 
                            fontSize: '0.7rem', 
                            color: metric.evolution_pct > 0 ? '#10b981' : '#ef4444',
                            marginLeft: '0.5rem'
                          }} className="animate-pulse">
                            {metric.evolution_pct > 0 ? '↗' : '↘'} {Math.abs(metric.evolution_pct)}%
                          </span>
                        )}
                      </div>
                      {metric.evolution !== undefined && (
                        <div className="stat-sublabel animate-fade-in-up">
                          {metric.evolution >= 0 ? '+' : ''}{metric.evolution} vs hier
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Graphiques avec animations en cascade */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem' }} className="stagger-children">
                
                {/* Graphique: Articles par source */}
                {analyticsData.sourceChart && (
                  <div className="glass-card chart-container animate-fade-in-scale" style={{ padding: '2rem' }}>
                    <h3 style={{ marginBottom: '1.5rem', color: '#1f2937', fontSize: '1.25rem' }} className="chart-title animate-fade-in-left">
                      📊 Articles par Source
                    </h3>
                    <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }} className="chart-wrapper">
                      <SourceChart data={analyticsData.sourceChart.chart_data} />
                    </div>
                    <div style={{ marginTop: '1rem', textAlign: 'center', color: '#6b7280', fontSize: '0.9rem' }} className="chart-caption animate-fade-in-up">
                      {analyticsData.sourceChart.total_articles} articles • {analyticsData.sourceChart.period}
                    </div>
                  </div>
                )}

                {/* Graphique: Évolution temporelle */}
                {analyticsData.timelineChart && (
                  <div className="glass-card chart-container animate-fade-in-scale animate-delay-100" style={{ padding: '2rem' }}>
                    <h3 style={{ marginBottom: '1.5rem', color: '#1f2937', fontSize: '1.25rem' }} className="chart-title animate-fade-in-left">
                      📈 Évolution Temporelle
                    </h3>
                    <div style={{ height: '300px' }} className="chart-wrapper">
                      <TimelineChart data={analyticsData.timelineChart.chart_data} />
                    </div>
                    <div style={{ marginTop: '1rem', textAlign: 'center', color: '#6b7280', fontSize: '0.9rem' }} className="chart-caption animate-fade-in-up">
                      {analyticsData.timelineChart.total_articles} articles • {analyticsData.timelineChart.period}
                    </div>
                  </div>
                )}

                {/* Graphique: Sentiment par source */}
                {analyticsData.sentimentChart && analyticsData.sentimentChart.chart_data.labels.length > 0 && (
                  <div className="glass-card chart-container animate-fade-in-scale animate-delay-200" style={{ padding: '2rem' }}>
                    <h3 style={{ marginBottom: '1.5rem', color: '#1f2937', fontSize: '1.25rem' }} className="chart-title animate-fade-in-left">
                      💭 Sentiment par Source
                    </h3>
                    <div style={{ height: '300px' }} className="chart-wrapper">
                      <SentimentChart data={analyticsData.sentimentChart.chart_data} />
                    </div>
                    <div style={{ marginTop: '1rem', textAlign: 'center', color: '#6b7280', fontSize: '0.9rem' }} className="chart-caption animate-fade-in-up">
                      {analyticsData.sentimentChart.analyzed_articles} articles analysés
                    </div>
                  </div>
                )}

                {/* Informations sur les données avec animation */}
                <div className="glass-card animate-fade-in-scale animate-delay-300" style={{ padding: '2rem' }}>
                  <h3 style={{ marginBottom: '1.5rem', color: '#1f2937', fontSize: '1.25rem' }} className="animate-fade-in-left">
                    ℹ️ Informations
                  </h3>
                  <div style={{ color: '#4b5563', lineHeight: '1.6' }} className="stagger-children">
                    <p style={{ marginBottom: '1rem' }} className="animate-fade-in-up">
                      <strong>Sources de données :</strong> Articles extraits automatiquement des principaux 
                      médias guadeloupéens (France-Antilles, RCI, La 1ère, KaribInfo).
                    </p>
                    <p style={{ marginBottom: '1rem' }} className="animate-fade-in-up animate-delay-100">
                      <strong>Fréquence de mise à jour :</strong> Scraping automatique quotidien, 
                      cache intelligent 24H.
                    </p>
                    <p className="animate-fade-in-up animate-delay-200">
                      <strong>Analyse de sentiment :</strong> Traitement local des titres avec 
                      dictionnaires français et patterns Guadeloupe.
                    </p>
                  </div>
                  
                  <button
                    onClick={loadAnalyticsData}
                    className="glass-button primary micro-bounce animate-bounce-in animate-delay-400"
                    style={{ marginTop: '1.5rem' }}
                    disabled={loading}
                  >
                    {loading ? <span className="animate-rotate">⏳</span> : '🔄'} Actualiser les données
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Transcriptions Radio */}
        {activeTab === 'transcription' && (
          <div className="animate-slide-in">
            {/* En-tête avec statut global */}
            <div className="section-header">
              <h2 className="section-title">📻 Transcriptions Radio</h2>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ 
                    width: '8px', 
                    height: '8px', 
                    borderRadius: '50%',
                    background: transcriptionStatus.global_status.any_in_progress ? '#10b981' : '#9ca3af',
                    animation: transcriptionStatus.global_status.any_in_progress ? 'pulse 2s infinite' : 'none'
                  }}></div>
                  <span style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    {transcriptionStatus.global_status.any_in_progress 
                      ? `${transcriptionStatus.global_status.active_sections} transcription(s) en cours`
                      : 'Aucune transcription en cours'
                    }
                  </span>
                </div>
                {transcriptionStatus.global_status.any_in_progress && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6', animation: 'pulse 2s infinite' }}></div>
                    <span style={{ color: '#3b82f6', fontSize: '0.8rem' }}>Auto-actualisation (30s)</span>
                  </div>
                )}
              </div>
            </div>

            {/* Boutons d'action */}
            <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <button
                  onClick={captureRadioNow}
                  disabled={backgroundTasks.capturing}
                  className={backgroundTasks.capturing ? 'btn-secondary' : 'btn-primary'}
                  style={{ opacity: backgroundTasks.capturing ? 0.6 : 1 }}
                >
                  {backgroundTasks.capturing ? '⏳ Capture...' : '📻 Capturer Tout'}
                </button>
                <button
                  onClick={() => {
                    loadTranscriptionSections();
                    loadTranscriptionStatus();
                  }}
                  className="btn-secondary"
                >
                  🔄 Actualiser
                </button>
                <label className="btn-primary cursor-pointer">
                  📤 Upload Audio
                  <input type="file" accept="audio/*" onChange={uploadAudio} style={{ display: 'none' }} />
                </label>
              </div>
            </div>

            {/* Sections de transcription prédéfinies */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem', marginBottom: '3rem' }}>
              {/* Section 7H RCI */}
              <div className="glass-card radio-priority-card" style={{ padding: '2rem' }}>
                <div className="priority-badge" style={{ marginBottom: '1.5rem' }}>
                  🎙️ PRIORITÉ ABSOLUE
                </div>
                {/* Information */}
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '0.5rem', color: '#1a1a1a' }}>
                    🎙️ 7H RCI
                  </h3>
                  <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    RCI Guadeloupe - Journal matinal | 07:00 - 07:20 (20 min)
                  </div>
                </div>

                {/* Statut et actions */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                  <div>
                    {transcriptionStatus.sections?.rci_7h?.in_progress ? (
                      <div className="status-indicator status-warning">
                        <div style={{ width: '6px', height: '6px', background: '#f59e0b', borderRadius: '50%', animation: 'pulse 2s infinite' }}></div>
                        {transcriptionStatus.sections?.rci_7h?.step_details || 'En cours...'}
                      </div>
                    ) : (
                      <div className="status-indicator status-success">
                        ✅ Prêt à capturer
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => captureSection('rci')}
                    disabled={loading || transcriptionStatus.sections?.rci_7h?.in_progress}
                    className={transcriptionStatus.sections?.rci_7h?.in_progress ? 'btn-secondary' : 'btn-primary'}
                    style={{ opacity: transcriptionStatus.sections?.rci_7h?.in_progress ? 0.6 : 1 }}
                  >
                    📻 Capturer
                  </button>
                </div>

                {/* Transcriptions */}
                <div className="transcription-list">
                  {transcriptionSections["7H RCI"]?.length > 0 ? (
                    transcriptionSections["7H RCI"].slice(0, 2).map(t => (
                      <div key={t.id} className="transcription-item" style={{ padding: '1.5rem' }}>
                        {/* Information */}
                        <div className="transcription-information">
                          📻 {t.stream_name} - {new Date(t.captured_at).toLocaleDateString('fr-FR')}
                        </div>
                        
                        {/* Explication */}
                        <div className="transcription-explication">
                          {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 150)}..."`}
                        </div>

                        {/* Métadonnées */}
                        <div className="transcription-meta">
                          <span style={{ color: '#f59e0b', fontWeight: '500' }}>
                            {t.transcription_method === 'segmented_openai_whisper_api' ? '🎬 Segmenté' : '🎤 Simple'}
                          </span>
                          <span>{new Date(t.captured_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                          {t.segments_count && (
                            <span>{t.segments_count} segments</span>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📻</div>
                      <p style={{ color: '#6b7280' }}>Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Section 7H Guadeloupe Première */}
              <div className="glass-card" style={{ padding: '2rem' }}>
                {/* Information */}
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '0.5rem', color: '#1a1a1a' }}>
                    📻 7H Guadeloupe Première
                  </h3>
                  <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    Guadeloupe Première - Actualités matinales | 07:00 - 07:30 (30 min)
                  </div>
                </div>

                {/* Statut et actions */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                  <div>
                    {transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? (
                      <div className="status-indicator status-warning">
                        <div style={{ width: '6px', height: '6px', background: '#f59e0b', borderRadius: '50%', animation: 'pulse 2s infinite' }}></div>
                        {transcriptionStatus.sections?.guadeloupe_premiere_7h?.step_details || 'En cours...'}
                      </div>
                    ) : (
                      <div className="status-indicator status-info">
                        ✅ Prêt à capturer
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => captureSection('guadeloupe')}
                    disabled={loading || transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress}
                    className={transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? 'btn-secondary' : 'btn-primary'}
                    style={{ opacity: transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? 0.6 : 1 }}
                  >
                    📻 Capturer
                  </button>
                </div>

                {/* Transcriptions */}
                <div className="transcription-list">
                  {transcriptionSections["7H Guadeloupe Première"]?.length > 0 ? (
                    transcriptionSections["7H Guadeloupe Première"].slice(0, 2).map(t => (
                      <div key={t.id} className="transcription-item" style={{ padding: '1.5rem' }}>
                        {/* Information */}
                        <div className="transcription-information">
                          📻 {t.stream_name} - {new Date(t.captured_at).toLocaleDateString('fr-FR')}
                        </div>
                        
                        {/* Explication */}
                        <div className="transcription-explication">
                          {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 150)}..."`}
                        </div>

                        {/* Métadonnées */}
                        <div className="transcription-meta">
                          <span style={{ color: '#3b82f6', fontWeight: '500' }}>
                            {t.transcription_method === 'segmented_openai_whisper_api' ? '🎬 Segmenté' : '🎤 Simple'}
                          </span>
                          <span>{new Date(t.captured_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                          {t.segments_count && (
                            <span>{t.segments_count} segments</span>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📻</div>
                      <p style={{ color: '#6b7280' }}>Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Toutes les transcriptions du jour */}
            <div className="glass-card" style={{ padding: '2rem' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '1.5rem', color: '#1a1a1a' }}>
                📋 Toutes les transcriptions du jour
              </h3>
              
              <div className="transcription-list">
                {Object.entries(transcriptionSections).map(([sectionName, transcriptions]) => 
                  transcriptions?.map(t => (
                    <div key={t.id} className="transcription-item">
                      {/* Information */}
                      <div className="transcription-information">
                        📻 {t.stream_name || sectionName} - {new Date(t.captured_at || t.uploaded_at).toLocaleDateString('fr-FR')}
                      </div>
                      
                      {/* Explication */}
                      <div className="transcription-explication">
                        {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 200)}..."`}
                      </div>

                      {/* Métadonnées */}
                      <div className="transcription-meta">
                        <span className="article-source">{sectionName}</span>
                        <span>{new Date(t.captured_at || t.uploaded_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                        {t.segments_count && (
                          <span style={{ color: '#f59e0b', fontWeight: '500' }}>🎬 {t.segments_count} segments</span>
                        )}
                        {t.ai_relevance_score && (
                          <span style={{ color: '#10b981', fontWeight: '500' }}>
                            ⭐ {Math.round(t.ai_relevance_score * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
                
                {Object.values(transcriptionSections || {}).every(section => !section || section.length === 0) && (
                  <div className="glass-card" style={{ padding: '3rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📻</div>
                    <p style={{ color: '#6b7280', fontSize: '1.1rem' }}>Aucune transcription disponible</p>
                    <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginTop: '0.5rem' }}>
                      Capturez ou uploadez des fichiers audio pour commencer
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Search */}
        {activeTab === 'search' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">🔍 Recherche</h2>
              <div className="text-sm text-gray-600">
                Recherche dans articles et réseaux sociaux
              </div>
            </div>

            {/* Barre de recherche étendue */}
            <div className="bg-white p-6 rounded-xl shadow-lg">
              <div className="flex gap-4">
                <div className="flex-1">
                  <input
                    type="text"
                    placeholder="Rechercher dans les articles et réseaux sociaux..."
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      if (e.target.value.length >= 2) {
                        loadSearchSuggestions(e.target.value);
                      }
                    }}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        handleSearch(searchQuery);
                      }
                    }}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  
                  {/* Suggestions de recherche */}
                  {searchSuggestions.length > 0 && searchQuery.length >= 2 && (
                    <div className="absolute top-full left-0 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                      {searchSuggestions.map((suggestion, index) => (
                        <button
                          key={index}
                          onClick={() => {
                            setSearchQuery(suggestion);
                            handleSearch(suggestion);
                            setSearchSuggestions([]);
                          }}
                          className="w-full text-left px-4 py-2 hover:bg-gray-100 first:rounded-t-lg last:rounded-b-lg"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleSearch(searchQuery)}
                  disabled={searchLoading}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors disabled:opacity-50"
                >
                  {searchLoading ? '⏳ Recherche...' : '🔍 Rechercher'}
                </button>
              </div>
            </div>

            {/* Résultats de recherche */}
            {searchResults && (
              <div className="space-y-6">
                <div className="bg-blue-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-blue-800">
                    {searchResults.total_results} résultats pour "{searchResults.query}"
                  </h3>
                  <p className="text-sm text-blue-600 mt-1">
                    Recherché dans : {searchResults.searched_in.join(', ')}
                  </p>
                </div>

                {/* Articles trouvés */}
                {searchResults.articles && searchResults.articles.length > 0 && (
                  <div className="bg-white rounded-xl shadow-lg">
                    <div className="p-6 border-b border-gray-200">
                      <h3 className="text-lg font-bold text-gray-800">
                        📰 Articles ({searchResults.articles.length})
                      </h3>
                    </div>
                    <div className="p-6 space-y-4">
                      {searchResults.articles.map((article, index) => (
                        <div key={index} className="border-l-4 border-blue-500 pl-4">
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <SourceLogo source={article.source} size={32} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <h4 className="font-semibold text-gray-800">
                                <a 
                                  href={article.url} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  className="hover:text-blue-600 transition-colors"
                                >
                                  {article.title}
                                </a>
                              </h4>
                              <p className="text-sm text-gray-600 mt-1">
                                <span style={{
                                  background: getSiteLogo(article.source).bg,
                                  color: getSiteLogo(article.source).color,
                                  padding: '0.25rem 0.5rem',
                                  borderRadius: 'var(--radius-sm)',
                                  fontSize: '0.75rem',
                                  fontWeight: '500',
                                  marginRight: '0.5rem'
                                }}>
                                  {article.source}
                                </span>
                                • {new Date(article.scraped_at).toLocaleDateString('fr-FR')}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Posts réseaux sociaux trouvés */}
                {searchResults.social_posts && searchResults.social_posts.length > 0 && (
                  <div className="bg-white rounded-xl shadow-lg">
                    <div className="p-6 border-b border-gray-200">
                      <h3 className="text-lg font-bold text-gray-800">
                        📱 Réseaux Sociaux ({searchResults.social_posts.length})
                      </h3>
                    </div>
                    <div className="p-6 space-y-4">
                      {searchResults.social_posts.map((post, index) => (
                        <div key={index} className="border border-gray-200 rounded-lg p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-sm font-medium text-gray-800">@{post.author}</span>
                            <span className="text-xs text-gray-500">• {post.platform}</span>
                            <span className="text-xs text-gray-500">
                              • {new Date(post.created_at).toLocaleDateString('fr-FR')}
                            </span>
                          </div>
                          <p className="text-gray-700">{post.content}</p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>❤️ {post.engagement?.total || 0}</span>
                            {post.demo_data && <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded">DEMO</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Suggestions si aucun résultat */}
                {searchResults.total_results === 0 && searchResults.suggestions && (
                  <div className="bg-gray-50 p-6 rounded-lg text-center">
                    <p className="text-gray-600 mb-4">Aucun résultat trouvé.</p>
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Essayez ces suggestions :</p>
                      <div className="flex flex-wrap justify-center gap-2">
                        {searchResults.suggestions.map((suggestion, index) => (
                          <button
                            key={index}
                            onClick={() => {
                              setSearchQuery(suggestion);
                              handleSearch(suggestion);
                            }}
                            className="px-3 py-1 bg-white border border-gray-300 rounded-full text-sm hover:bg-gray-100 transition-colors"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Digest Narratif avec blocs structurés */}
        {activeTab === 'digest' && (
          <div className="digest-narrative-section">
            {createFloatingElements()}
            
            {/* Header du digest */}
            <div className="digest-hero-header scroll-reveal">
              <div className="digest-hero-content">
                <h1 className="digest-hero-title">📄 Digest Quotidien</h1>
                <p className="digest-hero-subtitle">Synthèse intelligente des actualités guadeloupéennes</p>
                <div className="digest-hero-date">
                  {new Date().toLocaleDateString('fr-FR', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                  })}
                </div>
              </div>
            </div>

            <div className="digest-content">
              {/* Section Transcriptions Radio */}
              <div className="digest-section scroll-reveal-left">
                <div className="digest-section-header">
                  <div className="section-icon">🎙️</div>
                  <div className="section-info">
                    <h2 className="section-title">Transcriptions Radio</h2>
                    <p className="section-subtitle">Analyses des émissions radiophoniques</p>
                  </div>
                  <div className="section-count">
                    {Object.values(transcriptionSections || {}).reduce((acc, arr) => acc + (arr?.length || 0), 0)} transcriptions
                  </div>
                </div>

                <div className="transcription-blocks">
                  {(() => {
                    const all = Object.values(transcriptionSections || {}).flat();
                    const items = all
                      .slice()
                      .sort((a, b) => new Date(b.captured_at || b.uploaded_at || 0) - new Date(a.captured_at || a.uploaded_at || 0))
                      .slice(0, 4);

                    if (items.length === 0) {
                      return (
                        <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                          <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📻</div>
                          <p style={{ color: '#6b7280' }}>Aucune transcription aujourd'hui</p>
                        </div>
                      );
                    }

                    const methodLabel = (m) => (m === 'segmented_openai_whisper_api' ? '🎬 Segmenté' : '🎤 Simple');

                    return items.map((t) => (
                      <div key={t.id} className="transcription-block scroll-reveal">
                        <div className="transcription-header">
                          <div className="transcription-source">
                            <div className="source-badge radio">
                              <span className="source-icon">📻</span>
                              <span className="source-name">{t.stream_name || t.section || 'Radio'}</span>
                            </div>
                            <div className="transcription-time">
                              {new Date(t.captured_at || t.uploaded_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                            </div>
                          </div>
                          <div className="transcription-status">
                            <span className="status-completed">✅ TRAITÉ</span>
                          </div>
                        </div>

                        <div className="transcription-content">
                          <h3 className="transcription-title">{t.section || t.stream_name}</h3>

                          <div className="transcription-extract">
                            <div className="extract-header">
                              <span className="extract-icon">💬</span>
                              <span className="extract-title">Extrait</span>
                            </div>
                            <div className="extract-content">
                              <p>{t.gpt_analysis || t.ai_summary || (t.transcription_text ? `"${t.transcription_text.substring(0, 220)}..."` : '—')}</p>
                            </div>
                          </div>

                          <div className="transcription-footer">
                            <div className="transcription-metrics">
                              <span className="metric-item">
                                <span className="metric-icon">🧩</span>
                                <span className="metric-value">{methodLabel(t.transcription_method)}</span>
                              </span>
                              {t.segments_count ? (
                                <span className="metric-item">
                                  <span className="metric-icon">🎬</span>
                                  <span className="metric-value">{t.segments_count} segments</span>
                                </span>
                              ) : null}
                            </div>
                            <div className="transcription-actions">
                              <button className="action-btn secondary">
                                <span>📄</span> Transcription
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              </div>

              {/* Section Articles du Jour */}
              <div className="digest-section scroll-reveal-right">
                <div className="digest-section-header">
                  <div className="section-icon">📰</div>
                  <div className="section-info">
                    <h2 className="section-title">Articles du Jour</h2>
                    <p className="section-subtitle">Actualités des médias locaux</p>
                  </div>
                  <div className="section-count">
                    {filteredArticles.length} articles
                  </div>
                </div>

                <div className="articles-digest-grid">
                  {filteredArticles.slice(0, 6).map((article, index) => (
                    <div key={index} className="article-digest-card scroll-reveal">
                      <div className="article-digest-header">
                        <SourceLogo source={article.source} size={32} />
                        <div className="article-meta">
                          <span className="article-source-name">{article.source}</span>
                          <span className="article-time">{new Date(article.date).toLocaleTimeString('fr-FR', {
                            hour: '2-digit',
                            minute: '2-digit'
                          })}</span>
                        </div>
                      </div>
                      <h4 className="article-digest-title">{article.title}</h4>
                      <p className="article-digest-summary">
                        {article.content ? article.content.substring(0, 120) + '...' : 'Résumé non disponible'}
                      </p>
                      <div className="article-digest-footer">
                        <span className="article-category">{article.category || 'Actualités'}</span>
                        <button className="read-more-btn">Lire →</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Section Actions */}
              <div className="digest-actions scroll-reveal-scale">
                <button 
                  onClick={createDigestNow}
                  className="digest-action-btn primary"
                >
                  <span>📊</span> Générer Rapport Complet
                </button>
                <button 
                  className="digest-action-btn secondary"
                >
                  <span>📱</span> Partager Digest
                </button>
                <a
                  href={`${BACKEND_URL}/api/digest/${selectedDate}/pdf`}
                  className="digest-action-btn tertiary"
                >
                  <span>📄</span> Télécharger PDF
                </a>
              </div>
            </div>
          </div>
        )}

        {/* Planificateur */}
        {activeTab === 'scheduler' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800">⏰ Planificateur Automatique</h2>
            
            {schedulerStatus.jobs && (
              <div className="grid gap-6">
                <div className="bg-white p-6 rounded-xl shadow-lg">
                  <h3 className="text-lg font-bold text-gray-800 mb-4">📅 Tâches Programmées</h3>
                  <div className="space-y-4">
                    {schedulerStatus.jobs.map(job => (
                      <div key={job.id} className="flex justify-between items-center p-4 border border-gray-200 rounded-lg">
                        <div>
                          <h4 className="font-semibold text-gray-800">{job.name}</h4>
                          <p className="text-sm text-gray-600">
                            Prochaine exécution: {job.next_run ? new Date(job.next_run).toLocaleString('fr-FR') : 'Non programmée'}
                          </p>
                        </div>
                        <button
                          onClick={() => runSchedulerJob(job.id)}
                          className="bg-indigo-500 hover:bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                        >
                          ▶️ Exécuter
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {schedulerStatus.recent_logs && (
                  <div className="bg-white p-6 rounded-xl shadow-lg">
                    <h3 className="text-lg font-bold text-gray-800 mb-4">📋 Logs Récents</h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {schedulerStatus.recent_logs.map((log, index) => (
                        <div 
                          key={index} 
                          className={`p-3 rounded-lg text-sm ${
                            log.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
                          }`}
                        >
                          <div className="flex justify-between items-start">
                            <span className="font-medium">{log.job_name}</span>
                            <span className="text-xs opacity-75">
                              {new Date(log.timestamp).toLocaleString('fr-FR')}
                            </span>
                          </div>
                          {log.details && <p className="mt-1 opacity-90">{log.details}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}


        {/* Page Commentaires */}
        {/* Section Réseaux Sociaux - VERSION MODERNISÉE */}
        {activeTab === 'comments' && (
          <div className="modern-social-section">
            {createFloatingElements()}
            
            {/* Header moderne avec gradient */}
            <div className="social-hero-header scroll-reveal">
              <div className="social-hero-content">
                <h1 className="social-hero-title">
                  🌐 Intelligence Sociale
                </h1>
                <p className="social-hero-subtitle">
                  Surveillance et analyse avancée des réseaux sociaux guadeloupéens
                </p>
                <div className="social-hero-stats scroll-reveal-scale">
                  <div className="hero-stat">
                    <div className="hero-stat-value">{(commentsAnalysis && commentsAnalysis.total_comments) || 0}</div>
                    <div className="hero-stat-label">Posts Analysés</div>
                  </div>
                  <div className="hero-stat">
                    <div className="hero-stat-value">{(socialStats && socialStats.total_posts) || 0}</div>
                    <div className="hero-stat-label">Posts Récents</div>
                  </div>
                  <div className="hero-stat">
                    <div className="hero-stat-value">{(socialStats && socialStats.total_mentions) || 0}</div>
                    <div className="hero-stat-label">Mentions</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Tableau de bord des réseaux sociaux */}
            <div className="social-dashboard">
              
              {/* Actions principales */}
              <div className="social-actions-grid scroll-reveal-left">
                <div className="social-action-card social-action-primary">
                  <div className="social-action-icon">🔍</div>
                  <div className="social-action-content">
                    <h3>Surveillance Active</h3>
                    <p>Surveiller les mentions et hashtags</p>
                    <button 
                      onClick={startSocialScraping}
                      className="social-action-btn"
                    >
                      📱 Démarrer Scraping
                    </button>
                  </div>
                </div>
                
                <div className="social-action-card social-action-success">
                  <div className="social-action-icon">🧠</div>
                  <div className="social-action-content">
                    <h3>Analyse Sentiment</h3>
                    <p>Intelligence artificielle des émotions</p>
                    <button 
                      onClick={analyzeComments}
                      className="social-action-btn"
                    >
                      📊 Analyser Maintenant
                    </button>
                  </div>
                </div>
                
                <div className="social-action-card social-action-info">
                  <div className="social-action-icon">📈</div>
                  <div className="social-action-content">
                    <h3>Tendances</h3>
                    <p>Sujets populaires et viraux</p>
                    <button 
                      onClick={() => handleSocialSearch('#Guadeloupe')}
                      className="social-action-btn"
                    >
                      🔥 Voir Tendances
                    </button>
                  </div>
                </div>
              </div>

              {/* Barre de recherche modernisée */}
              <div className="modern-search-section scroll-reveal-right">
                <div className="search-header">
                  <h3 className="search-title">🎯 Recherche Intelligente</h3>
                  <div className="search-tags stagger-reveal">
                    {['#Guadeloupe', 'politique', 'économie', 'culture', 'sport'].map((tag) => (
                      <button 
                        key={tag}
                        onClick={() => {
                          setSocialSearchQuery(tag);
                          handleSocialSearch(tag);
                        }}
                        className="search-tag"
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
                
                <div className="modern-search-bar">
                  <div className="search-input-wrapper">
                    <input
                      type="text"
                      placeholder="Rechercher des sujets, hashtags, personnalités..."
                      value={socialSearchQuery}
                      onChange={(e) => setSocialSearchQuery(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          handleSocialSearch(socialSearchQuery);
                        }
                      }}
                      className="modern-search-input"
                    />
                    <button 
                      onClick={() => handleSocialSearch(socialSearchQuery)}
                      disabled={socialSearchLoading}
                      className="search-btn"
                    >
                      {socialSearchLoading ? '⏳' : '🔍'}
                    </button>
                  </div>
                </div>
                
                {socialSearchError && (
                  <div className="search-error">
                    <span>⚠️ {socialSearchError}</span>
                    <button onClick={() => setSocialSearchError(null)}>✕</button>
                  </div>
                )}
              </div>

              {/* Plateformes sociales avec métriques */}
              <div className="social-platforms-grid">
                <div className="platform-card platform-facebook">
                  <div className="platform-header">
                    <div className="platform-icon">📘</div>
                    <div className="platform-info">
                      <h4>Facebook</h4>
                      <span className="platform-status">Actif</span>
                    </div>
                  </div>
                  <div className="platform-metrics">
                    <div className="metric">
                      <span className="metric-value">{(socialStats && socialStats.facebook_posts) || 0}</span>
                      <span className="metric-label">Posts</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{(socialStats && socialStats.facebook_engagement) || 0}</span>
                      <span className="metric-label">Engagement</span>
                    </div>
                  </div>
                </div>
                
                <div className="platform-card platform-twitter">
                  <div className="platform-header">
                    <div className="platform-icon">🐦</div>
                    <div className="platform-info">
                      <h4>X (Twitter)</h4>
                      <span className="platform-status">Actif</span>
                    </div>
                  </div>
                  <div className="platform-metrics">
                    <div className="metric">
                      <span className="metric-value">{socialStats.twitter_posts || 0}</span>
                      <span className="metric-label">Tweets</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{socialStats.twitter_retweets || 0}</span>
                      <span className="metric-label">RT</span>
                    </div>
                  </div>
                </div>
                
                <div className="platform-card platform-instagram">
                  <div className="platform-header">
                    <div className="platform-icon">📸</div>
                    <div className="platform-info">
                      <h4>Instagram</h4>
                      <span className="platform-status">En cours</span>
                    </div>
                  </div>
                  <div className="platform-metrics">
                    <div className="metric">
                      <span className="metric-value">{socialStats.instagram_posts || 0}</span>
                      <span className="metric-label">Posts</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{socialStats.instagram_stories || 0}</span>
                      <span className="metric-label">Stories</span>
                    </div>
                  </div>
                </div>
                
                <div className="platform-card platform-youtube">
                  <div className="platform-header">
                    <div className="platform-icon">📺</div>
                    <div className="platform-info">
                      <h4>YouTube</h4>
                      <span className="platform-status">Bientôt</span>
                    </div>
                  </div>
                  <div className="platform-metrics">
                    <div className="metric">
                      <span className="metric-value">{socialStats.youtube_videos || 0}</span>
                      <span className="metric-label">Vidéos</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{socialStats.youtube_views || 0}</span>
                      <span className="metric-label">Vues</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Analyse en temps réel */}
              {commentsAnalysis && commentsAnalysis.total_comments > 0 && (
                <div className="realtime-analysis scroll-reveal-scale">
                  <h3 className="analysis-title">📊 Analyse en Temps Réel</h3>
                  
                  <div className="analysis-cards stagger-reveal">
                    <div className="analysis-card sentiment-positive">
                      <div className="analysis-icon">😊</div>
                      <div className="analysis-content">
                        <div className="analysis-value">{Math.round(((commentsAnalysis && commentsAnalysis.sentiment_positive) || 0) * 100)}%</div>
                        <div className="analysis-label">Sentiment Positif</div>
                      </div>
                    </div>
                    
                    <div className="analysis-card sentiment-neutral">
                      <div className="analysis-icon">😐</div>
                      <div className="analysis-content">
                        <div className="analysis-value">{Math.round(((commentsAnalysis && commentsAnalysis.sentiment_neutral) || 0) * 100)}%</div>
                        <div className="analysis-label">Sentiment Neutre</div>
                      </div>
                    </div>
                    
                    <div className="analysis-card sentiment-negative">
                      <div className="analysis-icon">😞</div>
                      <div className="analysis-content">
                        <div className="analysis-value">{Math.round(((commentsAnalysis && commentsAnalysis.sentiment_negative) || 0) * 100)}%</div>
                        <div className="analysis-label">Sentiment Négatif</div>
                      </div>
                    </div>
                    
                    <div className="analysis-card topics">
                      <div className="analysis-icon">🏷️</div>
                      <div className="analysis-content">
                        <div className="analysis-value">{(commentsAnalysis && commentsAnalysis.top_topics && commentsAnalysis.top_topics.length) || 0}</div>
                        <div className="analysis-label">Sujets Populaires</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Résultats de recherche modernisés */}
              {socialSearchResults && (
                <div className="modern-search-results scroll-reveal-left">
                  <div className="results-header">
                    <h3>🎯 Résultats : "{socialSearchResults.query}"</h3>
                    <div className="results-count">{socialSearchResults.total_results} résultats</div>
                  </div>
                  
                  <div className="results-grid stagger-reveal">
                    {socialSearchResults.posts && socialSearchResults.posts.map((post, index) => (
                      <div key={index} className="result-card">
                        <div className="result-header">
                          <div className="result-platform">{post.platform}</div>
                          <div className="result-date">{new Date(post.date).toLocaleDateString()}</div>
                        </div>
                        <div className="result-content">
                          <p>{post.content}</p>
                        </div>
                        <div className="result-metrics">
                          <span className="metric">👍 {post.likes || 0}</span>
                          <span className="metric">💬 {post.comments || 0}</span>
                          <span className="metric">🔄 {post.shares || 0}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Commentaires récents avec design moderne et logos */}
              {comments && comments.length > 0 && (
                <div className="recent-comments-section scroll-reveal-right">
                  <h3 className="comments-title">💬 Commentaires Récents ({comments.length})</h3>
                  
                  <div className="comments-grid stagger-reveal">
                    {comments.map((comment, index) => (
                      <div key={index} className="modern-comment-card">
                        {/* Header avec logo de la source */}
                        <div className="comment-header">
                          <div className="comment-source-info">
                            <SourceLogo source={comment.platform || 'Social'} size={40} />
                            <div className="comment-platform-details">
                              <span className="comment-platform-name">{comment.platform || 'Social Media'}</span>
                              <span className="comment-date">{new Date(comment.date).toLocaleDateString('fr-FR', {
                                day: 'numeric',
                                month: 'short',
                                hour: '2-digit',
                                minute: '2-digit'
                              })}</span>
                            </div>
                          </div>
                          <div className="comment-sentiment-badge">
                            <span className="sentiment-emoji">
                              {comment.sentiment === 'positive' ? '😊' : 
                               comment.sentiment === 'negative' ? '😞' : '😐'}
                            </span>
                            <span className="sentiment-label">
                              {comment.sentiment === 'positive' ? 'Positif' : 
                               comment.sentiment === 'negative' ? 'Négatif' : 'Neutre'}
                            </span>
                          </div>
                        </div>

                        {/* Contenu du commentaire */}
                        <div className="comment-content">
                          <p>{comment.content}</p>
                        </div>

                        {/* Footer avec métriques */}
                        <div className="comment-footer">
                          <div className="comment-metrics">
                            <span className="metric-item">
                              <span className="metric-icon">📊</span>
                              <span className="metric-label">Score: {comment.sentiment_score ? Number(comment.sentiment_score).toFixed(2) : '0.00'}</span>
                            </span>
                            {comment.engagement && (
                              <>
                                <span className="metric-item">
                                  <span className="metric-icon">👍</span>
                                  <span className="metric-label">{comment.engagement.likes || 0}</span>
                                </span>
                                <span className="metric-item">
                                  <span className="metric-icon">💬</span>
                                  <span className="metric-label">{comment.engagement.replies || 0}</span>
                                </span>
                                <span className="metric-item">
                                  <span className="metric-icon">🔄</span>
                                  <span className="metric-label">{comment.engagement.shares || 0}</span>
                                </span>
                              </>
                            )}
                          </div>
                          
                          {/* Tags et catégories si disponibles */}
                          {comment.tags && comment.tags.length > 0 && (
                            <div className="comment-tags">
                              {comment.tags.slice(0, 3).map((tag, i) => (
                                <span key={i} className="comment-tag">#{tag}</span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Indicateur de tendance */}
                        {comment.trending && (
                          <div className="trending-indicator">
                            <span className="trending-icon">🔥</span>
                            <span className="trending-label">Tendance</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Bouton pour charger plus de commentaires */}
                  <div className="load-more-section">
                    <button 
                      onClick={() => {
                        // Fonction pour charger plus de commentaires
                        console.log('Charger plus de commentaires');
                      }}
                      className="load-more-btn"
                    >
                      📄 Charger plus de commentaires
                    </button>
                  </div>
                </div>
              )}

              {/* État vide modernisé avec données de démonstration */}
              {(!comments || comments.length === 0) && !socialSearchResults && (
                <div className="social-demo-section">
                  {/* Démonstration avec des commentaires d'exemple */}
                  <div className="recent-comments-section scroll-reveal-right">
                    <h3 className="comments-title">💬 Aperçu des Commentaires Réseaux Sociaux</h3>
                    
                    <div className="comments-grid stagger-reveal">
                      {/* Commentaire exemple Facebook */}
                      <div className="modern-comment-card">
                        <div className="comment-header">
                          <div className="comment-source-info">
                            <SourceLogo source="Facebook" size={40} />
                            <div className="comment-platform-details">
                              <span className="comment-platform-name">Facebook</span>
                              <span className="comment-date">31 juil., 14:30</span>
                            </div>
                          </div>
                          <div className="comment-sentiment-badge" style={{
                            background: 'rgba(16, 185, 129, 0.15)',
                            color: '#059669',
                            border: '1px solid rgba(16, 185, 129, 0.3)'
                          }}>
                            <span className="sentiment-emoji">😊</span>
                            <span className="sentiment-label">Positif</span>
                          </div>
                        </div>

                        <div className="comment-content">
                          <p>Excellente initiative pour la protection de l'environnement en Guadeloupe ! 🌴 Les nouvelles mesures pour les plages sont très bien pensées.</p>
                        </div>

                        <div className="comment-footer">
                          <div className="comment-metrics">
                            <span className="metric-item">
                              <span className="metric-icon">📊</span>
                              <span className="metric-label">Score: 0.85</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">👍</span>
                              <span className="metric-label">24</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">💬</span>
                              <span className="metric-label">8</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">🔄</span>
                              <span className="metric-label">12</span>
                            </span>
                          </div>
                          
                          <div className="comment-tags">
                            <span className="comment-tag">#environnement</span>
                            <span className="comment-tag">#guadeloupe</span>
                            <span className="comment-tag">#écologie</span>
                          </div>
                        </div>

                        <div className="trending-indicator">
                          <span className="trending-icon">🔥</span>
                          <span className="trending-label">Tendance</span>
                        </div>
                      </div>

                      {/* Commentaire exemple Twitter */}
                      <div className="modern-comment-card">
                        <div className="comment-header">
                          <div className="comment-source-info">
                            <SourceLogo source="X (Twitter)" size={40} />
                            <div className="comment-platform-details">
                              <span className="comment-platform-name">X (Twitter)</span>
                              <span className="comment-date">31 juil., 12:15</span>
                            </div>
                          </div>
                          <div className="comment-sentiment-badge" style={{
                            background: 'rgba(107, 114, 128, 0.15)',
                            color: '#4b5563',
                            border: '1px solid rgba(107, 114, 128, 0.3)'
                          }}>
                            <span className="sentiment-emoji">😐</span>
                            <span className="sentiment-label">Neutre</span>
                          </div>
                        </div>

                        <div className="comment-content">
                          <p>Info importante sur les transports publics en #Guadeloupe. Les nouveaux horaires de bus sont disponibles sur le site de la collectivité.</p>
                        </div>

                        <div className="comment-footer">
                          <div className="comment-metrics">
                            <span className="metric-item">
                              <span className="metric-icon">📊</span>
                              <span className="metric-label">Score: 0.02</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">👍</span>
                              <span className="metric-label">5</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">💬</span>
                              <span className="metric-label">3</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">🔄</span>
                              <span className="metric-label">7</span>
                            </span>
                          </div>
                          
                          <div className="comment-tags">
                            <span className="comment-tag">#transport</span>
                            <span className="comment-tag">#info</span>
                          </div>
                        </div>
                      </div>

                      {/* Commentaire exemple Instagram */}
                      <div className="modern-comment-card">
                        <div className="comment-header">
                          <div className="comment-source-info">
                            <SourceLogo source="Instagram" size={40} />
                            <div className="comment-platform-details">
                              <span className="comment-platform-name">Instagram</span>
                              <span className="comment-date">31 juil., 10:45</span>
                            </div>
                          </div>
                          <div className="comment-sentiment-badge" style={{
                            background: 'rgba(239, 68, 68, 0.15)',
                            color: '#dc2626',
                            border: '1px solid rgba(239, 68, 68, 0.3)'
                          }}>
                            <span className="sentiment-emoji">😞</span>
                            <span className="sentiment-label">Négatif</span>
                          </div>
                        </div>

                        <div className="comment-content">
                          <p>Déçu par les coupures d'eau répétées dans le secteur de Basse-Terre... Quand est-ce que ça va s'améliorer ? 😤</p>
                        </div>

                        <div className="comment-footer">
                          <div className="comment-metrics">
                            <span className="metric-item">
                              <span className="metric-icon">📊</span>
                              <span className="metric-label">Score: -0.65</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">👍</span>
                              <span className="metric-label">15</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">💬</span>
                              <span className="metric-label">22</span>
                            </span>
                            <span className="metric-item">
                              <span className="metric-icon">🔄</span>
                              <span className="metric-label">8</span>
                            </span>
                          </div>
                          
                          <div className="comment-tags">
                            <span className="comment-tag">#eau</span>
                            <span className="comment-tag">#basseterre</span>
                            <span className="comment-tag">#service</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="load-more-section">
                      <button 
                        onClick={startSocialScraping}
                        className="load-more-btn"
                      >
                        🚀 Lancer la surveillance réelle
                      </button>
                    </div>
                  </div>
                  
                  <div className="empty-state scroll-reveal-scale">
                    <div className="empty-icon">🌐</div>
                    <h3>Démarrez la surveillance sociale</h3>
                    <p>Lancez le scraping pour collecter et analyser les vraies données des réseaux sociaux guadeloupéens</p>
                    <button 
                      onClick={startSocialScraping}
                      className="empty-action-btn"
                    >
                      🚀 Commencer l'analyse
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Analyse de Sentiment et Prédiction des Réactions */}
        {activeTab === 'sentiment' && (
          <div className="animate-slide-in">
            <div className="section-header">
              <h2 className="section-title">🧠 Analyse de Sentiment & Anticipation Réactions</h2>
              <p className="section-subtitle">Analyse GPT contextuelle pour la Guadeloupe</p>
            </div>

            {/* Interface d'analyse */}
            <div className="glass-card animate-slide-in" style={{ padding: '2rem', marginBottom: '2rem' }}>
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '0.5rem', 
                  color: '#e2e8f0', 
                  fontWeight: '600' 
                }}>
                  Texte à analyser :
                </label>
                <textarea
                  value={sentimentText}
                  onChange={(e) => setSentimentText(e.target.value)}
                  placeholder="Entrez un texte d'actualité, une déclaration politique, ou un événement local..."
                  rows="4"
                  style={{
                    width: '100%',
                    padding: '1rem',
                    borderRadius: '12px',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    background: 'rgba(15, 23, 42, 0.8)',
                    color: '#e2e8f0',
                    fontSize: '1rem',
                    resize: 'vertical'
                  }}
                />
              </div>

              {/* Exemples rapides */}
              <div style={{ marginBottom: '1.5rem' }}>
                <p style={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                  💡 Exemples Guadeloupe :
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {[
                    "Guy Losbar annonce de nouveaux investissements pour le développement durable",
                    "Le Conseil Départemental vote le budget pour soutenir les familles en difficulté",
                    "Grave accident de la route en Guadeloupe, plusieurs blessés dans un état critique",
                    "Excellent festival de musique créole à Pointe-à-Pitre",
                    "CD971 lance une politique sociale ambitieuse pour les jeunes"
                  ].map((example, i) => (
                    <button
                      key={i}
                      onClick={() => useSentimentExample(example)}
                      style={{
                        padding: '0.5rem 1rem',
                        background: 'rgba(59, 130, 246, 0.1)',
                        border: '1px solid rgba(59, 130, 246, 0.3)',
                        borderRadius: '6px',
                        color: '#93c5fd',
                        fontSize: '0.75rem',
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                      onMouseOver={(e) => {
                        e.target.style.background = 'rgba(59, 130, 246, 0.2)';
                      }}
                      onMouseOut={(e) => {
                        e.target.style.background = 'rgba(59, 130, 246, 0.1)';
                      }}
                    >
                      {example.length > 50 ? example.substring(0, 50) + '...' : example}
                    </button>
                  ))}
                </div>
              </div>

              {/* Boutons d'action */}
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <button
                  onClick={() => analyzeSentiment(false)}
                  disabled={sentimentLoading || !sentimentText.trim()}
                  className="btn-primary"
                  style={{ 
                    opacity: sentimentLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: sentimentLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {sentimentLoading ? '⏳ Analyse...' : '📊 Analyse Synchrone (3-8s)'}
                </button>
                
                <button
                  onClick={() => analyzeSentiment(true)}
                  disabled={sentimentLoading || !sentimentText.trim()}
                  className="btn-secondary"
                  style={{ 
                    opacity: sentimentLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: sentimentLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {sentimentLoading ? '⏳ Traitement...' : '⚡ Analyse Asynchrone (instantané si cache)'}
                </button>

                <button
                  onClick={predictReaction}
                  disabled={predictionLoading || !sentimentText.trim()}
                  className="btn-accent"
                  style={{ 
                    opacity: predictionLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: predictionLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {predictionLoading ? '⏳ Prédiction...' : '🔮 Prédire la Réaction Population'}
                </button>
              </div>
            </div>

            {/* Résultats de l'analyse de sentiment - VERSION AMÉLIORÉE */}
            {sentimentResult && (
              <div className="glass-card animate-slide-in" style={{ padding: '2rem', marginBottom: '2rem' }}>
                <h3 className="section-title" style={{ marginBottom: '1.5rem' }}>
                  🧠 Analyse de Sentiment & Recommandations
                </h3>

                {sentimentResult.mode === 'async' && sentimentResult.status === 'processing' ? (
                  <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <div className="animate-pulse" style={{
                      width: '40px',
                      height: '40px',
                      background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                      borderRadius: '50%',
                      margin: '0 auto 1rem'
                    }}></div>
                    <p style={{ color: '#e2e8f0' }}>⏳ {sentimentResult.message}</p>
                    <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                      Hash: {sentimentResult.hash}
                    </p>
                  </div>
                ) : sentimentResult.analysis ? (
                  // Utiliser le nouveau composant d'analyse amélioré
                  <EnhancedSentimentAnalysis analysis={sentimentResult.analysis} />
                ) : (
                  <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <p style={{ color: '#e2e8f0' }}>❌ {sentimentResult.error || 'Erreur lors de l\'analyse'}</p>
                  </div>
                )}
              </div>
            )}

            {/* Prédiction des réactions */}
            {reactionPrediction && (
              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <h3 className="section-title" style={{ marginBottom: '1.5rem' }}>
                  🔮 Anticipation de la Réaction de la Population
                </h3>

                {/* Réaction globale */}
                <div style={{
                  textAlign: 'center',
                  padding: '2rem',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '12px',
                  marginBottom: '2rem'
                }}>
                  <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>
                    {reactionPrediction.population_reaction.overall_reaction === 'très positive' ? '🎉' :
                     reactionPrediction.population_reaction.overall_reaction === 'positive' ? '😊' :
                     reactionPrediction.population_reaction.overall_reaction === 'neutre' ? '😐' :
                     reactionPrediction.population_reaction.overall_reaction === 'négative' ? '😞' : '😡'}
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                    Réaction Globale: {reactionPrediction.population_reaction.overall_reaction}
                  </div>
                  <div style={{ color: '#94a3b8' }}>
                    Score: {reactionPrediction.population_reaction.overall_score} | 
                    Polarisation: {reactionPrediction.population_reaction.polarization_risk} | 
                    Confiance: {Math.round(reactionPrediction.confidence * 100)}%
                  </div>
                </div>

                {/* Réactions par segment */}
                <div style={{ marginBottom: '2rem' }}>
                  <h4 style={{ color: '#8b5cf6', marginBottom: '1rem' }}>👥 Réactions par Segment de Population</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                    {Object.entries(reactionPrediction.population_reaction.by_demographic || {}).map(([segment, data]) => (
                      <div key={segment} style={{
                        padding: '1rem',
                        background: 'rgba(75, 85, 99, 0.1)',
                        borderRadius: '8px',
                        border: '1px solid rgba(139, 92, 246, 0.2)'
                      }}>
                        <div style={{ fontWeight: 'bold', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                          {segment.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </div>
                        <div style={{ color: '#c4b5fd', marginBottom: '0.5rem' }}>
                          {data.reaction_label} ({data.reaction_score})
                        </div>
                        <div style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
                          Engagement: {data.engagement_likelihood}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.5rem' }}>
                          Préoccupations: {data.key_concerns.join(', ')}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Données sources */}
                <div style={{ marginBottom: '2rem' }}>
                  <h4 style={{ color: '#10b981', marginBottom: '1rem' }}>📊 Sources de Données Utilisées</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                    <div style={{
                      padding: '1rem',
                      background: 'rgba(16, 185, 129, 0.1)',
                      borderRadius: '8px'
                    }}>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#6ee7b7' }}>
                        {reactionPrediction.data_sources.similar_articles}
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Articles similaires</div>
                    </div>
                    <div style={{
                      padding: '1rem',
                      background: 'rgba(59, 130, 246, 0.1)',
                      borderRadius: '8px'
                    }}>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#93c5fd' }}>
                        {reactionPrediction.data_sources.similar_social_posts}
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Posts réseaux sociaux</div>
                    </div>
                  </div>
                </div>

                {/* Recommandations stratégiques */}
                {reactionPrediction.strategic_recommendations.length > 0 && (
                  <div>
                    <h4 style={{ color: '#f59e0b', marginBottom: '1rem' }}>🎯 Recommandations Stratégiques</h4>
                    <div style={{ display: 'grid', gap: '0.5rem' }}>
                      {reactionPrediction.strategic_recommendations.map((recommendation, i) => (
                        <div key={i} style={{
                          padding: '1rem',
                          background: 'rgba(245, 158, 11, 0.1)',
                          borderRadius: '8px',
                          borderLeft: '4px solid #f59e0b',
                          color: '#e2e8f0'
                        }}>
                          {recommendation}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}

export default PrivateApp;
