import React, { useEffect, useMemo, useRef, useState } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import Login from "./pages/Login";
import "./App.css";

// Chart.js
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line, Doughnut } from "react-chartjs-2";

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

/*************************************************
 * CONFIG
 *************************************************/
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

/*************************************************
 * SMALL UTILITIES
 *************************************************/
const cls = (...a) => a.filter(Boolean).join(" ");

const useMounted = () => {
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => (mounted.current = false);
  }, []);
  return mounted;
};

const apiCall = async (path, options = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(path, {
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  } catch (e) {
    clearTimeout(timeout);
    if (e?.name === "AbortError") throw new Error("Délai dépassé (30s)");
    throw e;
  }
};

/*************************************************
 * GENERIC UI
 *************************************************/
const LoadingOverlay = ({ show, label = "Chargement..." }) =>
  show ? (
    <div className="loading-overlay">
      <div className="loading-card">
        <div className="spinner" />
        <div className="loading-label">{label}</div>
      </div>
    </div>
  ) : null;

const ErrorBanner = ({ error, onClose }) =>
  error ? (
    <div className="error-banner">
      <span>⚠️ {String(error)}</span>
      {onClose && (
        <button onClick={onClose} className="btn-secondary small">
          ✕
        </button>
      )}
    </div>
  ) : null;

const AppLogo = ({ size = 40 }) => (
  <div
    className="app-logo"
    style={{
      width: size,
      height: size,
      borderRadius: 12,
      background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: "white",
      position: "relative",
      overflow: "hidden",
      boxShadow: "0 6px 20px rgba(59,130,246,.35)",
      fontWeight: 800,
      letterSpacing: -0.5,
      fontSize: size * 0.45,
    }}
    title="Veille Média Guadeloupe"
  >
    🏝️
    <div className="logo-shine" />
  </div>
);

/*************************************************
 * SOURCE LOGO (small, resilient)
 *************************************************/
const SOURCE_STYLE_MAP = {
  "France-Antilles Guadeloupe": {
    domain: "guadeloupe.franceantilles.fr",
    fallback: "FA",
    color: "#dc2626",
  },
  "RCI Guadeloupe": { domain: "rci.fm", fallback: "RCI", color: "#2563eb" },
  "La 1ère Guadeloupe": {
    domain: "la1ere.francetvinfo.fr",
    fallback: "1ère",
    color: "#059669",
  },
  KaribInfo: { domain: "karibinfo.com", fallback: "KI", color: "#ea580c" },
};

const getSiteStyle = (source = "?") => {
  const key = Object.keys(SOURCE_STYLE_MAP).find((k) =>
    k.toLowerCase().includes(source.toLowerCase()) ||
    source.toLowerCase().includes(k.toLowerCase())
  );
  const cfg = key ? SOURCE_STYLE_MAP[key] : { fallback: source.slice(0, 2).toUpperCase(), color: "#6b7280" };
  return {
    logo: cfg.domain ? `https://www.google.com/s2/favicons?domain=${cfg.domain}&sz=64` : null,
    fallback: cfg.fallback,
    color: cfg.color,
  };
};

const SourceLogo = ({ source, size = 32 }) => {
  const [ok, setOk] = useState(true);
  const style = getSiteStyle(source);
  return (
    <div
      className="source-logo"
      style={{
        width: size,
        height: size,
        borderRadius: 8,
        border: `2px solid ${style.color}55`,
        background: `${style.color}11`,
        display: "grid",
        placeItems: "center",
        position: "relative",
        overflow: "hidden",
        fontWeight: 700,
        fontSize: size * 0.35,
        color: style.color,
      }}
      title={`Source: ${source}`}
    >
      <span>{style.fallback}</span>
      {style.logo && ok && (
        <img
          src={style.logo}
          alt={source}
          onError={() => setOk(false)}
          className="source-logo-img"
          style={{ position: "absolute", inset: 4, opacity: 0.95 }}
          loading="lazy"
        />
      )}
    </div>
  );
};

/*************************************************
 * CHARTS (thin wrappers around Chart.js)
 *************************************************/
const baseTooltip = {
  backgroundColor: "rgba(17,24,39,0.9)",
  titleColor: "#f9fafb",
  bodyColor: "#f9fafb",
  borderColor: "rgba(75,85,99,0.3)",
  borderWidth: 1,
};

const DoughnutChart = ({ data }) => (
  <Doughnut
    data={data}
    options={{
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: baseTooltip },
    }}
  />
);

const LineChart = ({ data }) => (
  <Line
    data={data}
    options={{
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: baseTooltip },
      scales: {
        y: { beginAtZero: true, grid: { color: "rgba(75,85,99,0.1)" } },
        x: { grid: { display: false } },
      },
      interaction: { intersect: false, mode: "index" },
    }}
  />
);

const StackedBarChart = ({ data }) => (
  <Bar
    data={data}
    options={{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { usePointStyle: true } },
        tooltip: baseTooltip,
      },
      scales: {
        y: { beginAtZero: true, stacked: true, grid: { color: "rgba(75,85,99,0.1)" } },
        x: { stacked: true, grid: { display: false } },
      },
    }}
  />
);

/*************************************************
 * DATA NORMALIZERS (safe defaults)
 *************************************************/
const EMPTY_DATA = { labels: [], datasets: [{ label: "Aucune donnée", data: [] }] };
const safeChart = (obj) => (obj && obj.chart_data) || EMPTY_DATA;

/*************************************************
 * LAYOUT
 *************************************************/
const Shell = ({ children, activeTab, onTabChange }) => {
  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "search", label: "Recherche" },
    { id: "articles", label: "Articles" },
    { id: "analytics", label: "Analytics" },
    { id: "sentiment", label: "Sentiment" },
    { id: "comments", label: "Réseaux Sociaux" },
    { id: "transcription", label: "Radio" },
    { id: "digest", label: "Digest" },
    { id: "scheduler", label: "Planificateur" },
  ];

  return (
    <div className="app">
      <header className="glass-header">
        <div className="header-content">
          <div className="header-left">
            <AppLogo size={44} />
            <div className="header-title-section">
              <h1 className="app-title">Veille Média Guadeloupe</h1>
              <p className="app-subtitle">IA • Surveillance médiatique • Guadeloupe</p>
            </div>
          </div>
          <div className="header-right">
            <span className="header-last-update">
              Dernière MAJ : {new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
        </div>
      </header>

      <nav className="tab-navigation">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={cls("tab-button", activeTab === t.id && "active")}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content-section">{children}</main>
    </div>
  );
};

/*************************************************
 * PAGES
 *************************************************/
const DashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const mounted = useMounted();

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await apiCall(`${BACKEND_URL}/api/dashboard-stats`);
        if (mounted.current) setStats(res?.stats || res);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [mounted]);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />
      <LoadingOverlay show={loading} />

      <section className="grid-cards">
        <div className="stat-card">
          <div className="stat-value">{stats?.articles_today ?? 0}</div>
          <div className="stat-label">Articles du jour</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.total_articles ?? 0}</div>
          <div className="stat-label">Total articles</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.active_sources ?? 0}</div>
          <div className="stat-label">Sources actives</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.transcriptions_today ?? 0}</div>
          <div className="stat-label">Transcriptions du jour</div>
        </div>
      </section>
    </div>
  );
};

const ArticlesPage = () => {
  const [filters, setFilters] = useState({ text: "", source: "all", start: "", end: "", sort: "date_desc" });
  const [items, setItems] = useState([]);
  const [pagination, setPagination] = useState({ total: 0, offset: 0, hasMore: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchArticles = async (offset = 0) => {
    setLoading(true);
    setError("");
    try {
      const p = new URLSearchParams({ limit: "50", offset: String(offset), sort_by: filters.sort });
      if (filters.text) p.append("search_text", filters.text);
      if (filters.source && filters.source !== "all") p.append("source", filters.source);
      if (filters.start) p.append("date_start", filters.start);
      if (filters.end) p.append("date_end", filters.end);
      const res = await apiCall(`${BACKEND_URL}/api/articles/filtered?${p.toString()}`);
      const list = res?.articles || [];
      setItems(offset === 0 ? list : (prev) => [...prev, ...list]);
      setPagination({
        total: res?.pagination?.total ?? list.length,
        offset: res?.pagination?.offset ?? offset,
        hasMore: res?.pagination?.hasMore ?? false,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />
      <section className="filters">
        <input
          className="glass-input"
          placeholder="Recherche (titre, texte)"
          value={filters.text}
          onChange={(e) => setFilters({ ...filters, text: e.target.value })}
        />
        <input
          type="date"
          className="glass-input"
          value={filters.start}
          onChange={(e) => setFilters({ ...filters, start: e.target.value })}
        />
        <input
          type="date"
          className="glass-input"
          value={filters.end}
          onChange={(e) => setFilters({ ...filters, end: e.target.value })}
        />
        <select
          className="glass-input"
          value={filters.sort}
          onChange={(e) => setFilters({ ...filters, sort: e.target.value })}
        >
          <option value="date_desc">Date ↓</option>
          <option value="date_asc">Date ↑</option>
          <option value="title_asc">Titre A-Z</option>
          <option value="title_desc">Titre Z-A</option>
        </select>
        <button className="btn-primary" onClick={() => fetchArticles(0)}>
          🔍 Appliquer
        </button>
      </section>

      <div className="list">
        {items.map((a, i) => (
          <article key={`${a.id ?? i}`} className="article-card">
            <div className="article-head">
              <SourceLogo source={a.source} size={40} />
              <div className="fx1">
                <h3 className="article-title">
                  <a href={a.url} target="_blank" rel="noreferrer">
                    {a.title}
                  </a>
                </h3>
                <div className="article-meta">
                  <span className="chip">{a.source}</span>
                  <span className="muted">
                    {new Date(a.published_at || a.scraped_at || Date.now()).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              </div>
            </div>
            <p className="muted">{a.summary || a.ai_summary || "Résumé non disponible."}</p>
          </article>
        ))}
      </div>

      {pagination.hasMore && (
        <div className="center">
          <button className="btn-secondary" onClick={() => fetchArticles(pagination.offset + 50)} disabled={loading}>
            {loading ? "⏳" : "📄"} Charger plus
          </button>
        </div>
      )}

      <LoadingOverlay show={loading} />
    </div>
  );
};

const AnalyticsPage = () => {
  const [data, setData] = useState({ sources: EMPTY_DATA, timeline: EMPTY_DATA, sentiment: EMPTY_DATA, meta: {} });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [a, b, c, m] = await Promise.all([
        apiCall(`${BACKEND_URL}/api/analytics/articles-by-source`),
        apiCall(`${BACKEND_URL}/api/analytics/articles-timeline`),
        apiCall(`${BACKEND_URL}/api/analytics/sentiment-by-source`),
        apiCall(`${BACKEND_URL}/api/analytics/dashboard-metrics`),
      ]);
      setData({
        sources: safeChart(a),
        timeline: safeChart(b),
        sentiment: safeChart(c),
        meta: (m?.data || m?.metrics || m) ?? {},
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <div className="stack v24">
      <ErrorBanner error={error} onClose={() => setError("")} />
      <div className="grid-charts">
        <div className="chart-card">
          <h3>📊 Articles par source</h3>
          <div className="chart-wrap"><DoughnutChart data={data.sources} /></div>
        </div>
        <div className="chart-card">
          <h3>📈 Évolution temporelle</h3>
          <div className="chart-wrap"><LineChart data={data.timeline} /></div>
        </div>
        <div className="chart-card">
          <h3>💭 Sentiment par source</h3>
          <div className="chart-wrap"><StackedBarChart data={data.sentiment} /></div>
        </div>
      </div>

      <div className="center">
        <button className="btn-primary" onClick={loadAll} disabled={loading}>
          {loading ? "⏳" : "🔄"} Actualiser
        </button>
      </div>

      <LoadingOverlay show={loading} />
    </div>
  );
};

const SentimentPage = () => {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const analyze = async () => {
    if (!text.trim()) return setError("Veuillez saisir un texte");
    setLoading(true);
    setError("");
    try {
      const res = await apiCall(`${BACKEND_URL}/api/sentiment/analyze`, {
        method: "POST",
        body: JSON.stringify({ text })
      });
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const predict = async () => {
    if (!text.trim()) return setError("Veuillez saisir un texte");
    setLoading(true);
    setError("");
    try {
      const res = await apiCall(`${BACKEND_URL}/api/sentiment/predict-reaction`, {
        method: "POST",
        body: JSON.stringify({ text, context: { source: "frontend" } })
      });
      setPrediction(res?.prediction || res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />

      <textarea
        className="text-input"
        rows={5}
        placeholder="Collez un texte d'actualité, une déclaration, etc."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="row g8">
        <button className="btn-primary" onClick={analyze} disabled={loading}>
          🤖 Analyser le sentiment
        </button>
        <button className="btn-secondary" onClick={predict} disabled={loading}>
          🔮 Prédire la réaction
        </button>
      </div>

      {result && (
        <div className="panel">
          <h3>Résultat analyse</h3>
          <pre className="pre-scrollable">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}

      {prediction && (
        <div className="panel">
          <h3>Prédiction de réaction</h3>
          <pre className="pre-scrollable">{JSON.stringify(prediction, null, 2)}</pre>
        </div>
      )}

      <LoadingOverlay show={loading} />
    </div>
  );
};

const CommentsPage = () => {
  const [stats, setStats] = useState({});
  const [comments, setComments] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [s, c] = await Promise.all([
        apiCall(`${BACKEND_URL}/api/social/stats`),
        apiCall(`${BACKEND_URL}/api/comments`),
      ]);
      setStats(s?.stats || s);
      setComments(c?.comments || c || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />

      <div className="grid-cards">
        <div className="stat-card"><div className="stat-value">{stats.total_posts ?? 0}</div><div className="stat-label">Posts</div></div>
        <div className="stat-card"><div className="stat-value">{stats.total_mentions ?? 0}</div><div className="stat-label">Mentions</div></div>
        <div className="stat-card"><div className="stat-value">{stats.facebook_posts ?? 0}</div><div className="stat-label">Facebook</div></div>
        <div className="stat-card"><div className="stat-value">{stats.twitter_posts ?? 0}</div><div className="stat-label">X / Twitter</div></div>
      </div>

      <div className="list">
        {comments.map((c, i) => (
          <div key={i} className="comment-card">
            <div className="row g8 ai-center">
              <SourceLogo source={c.platform || "Social"} />
              <div className="fx1">
                <div className="row g8 jc-between ai-center">
                  <strong>{c.platform || ""}</strong>
                  <span className="muted small">{new Date(c.date || Date.now()).toLocaleString("fr-FR")}</span>
                </div>
                <p className="mb0">{c.content}</p>
              </div>
            </div>
            {c.engagement && (
              <div className="muted small mt8">
                👍 {c.engagement.likes || 0} • 💬 {c.engagement.replies || 0} • 🔄 {c.engagement.shares || 0}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="center">
        <button className="btn-secondary" onClick={load} disabled={loading}>
          {loading ? "⏳" : "🔄"} Actualiser
        </button>
      </div>

      <LoadingOverlay show={loading} />
    </div>
  );
};

const TranscriptionPage = () => {
  const [sections, setSections] = useState({});
  const [status, setStatus] = useState({ global_status: { any_in_progress: false, active_sections: 0 } });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [sec, st] = await Promise.all([
        apiCall(`${BACKEND_URL}/api/transcriptions/sections`),
        apiCall(`${BACKEND_URL}/api/transcriptions/status`),
      ]);
      setSections(sec?.sections || {});
      setStatus(st?.status || st || {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const capture = async (sectionKey) => {
    setLoading(true);
    try {
      const res = await apiCall(`${BACKEND_URL}/api/transcriptions/capture-now?section=${encodeURIComponent(sectionKey)}`, { method: "POST" });
      alert(res?.message || "Capture lancée");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const all = Object.entries(sections || {});

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />
      <div className="row g8 ai-center jc-between">
        <div className="muted">
          Statut global : {status?.global_status?.any_in_progress ? "⏳ En cours" : "✅ Au repos"}
        </div>
        <button className="btn-secondary" onClick={load}>🔄 Actualiser</button>
      </div>

      {all.length === 0 && <div className="panel center">Aucune transcription disponible.</div>}

      <div className="list">
        {all.map(([label, list]) => (
          <div key={label} className="panel">
            <div className="row g8 ai-center jc-between">
              <h3 className="m0">{label}</h3>
              <button className="btn-primary" onClick={() => capture(label.includes("RCI") ? "rci" : "guadeloupe")}>📻 Capturer</button>
            </div>
            {(list || []).slice(0, 3).map((t) => (
              <div key={t.id} className="transcription-item">
                <div className="muted small">{t.stream_name || label} • {new Date(t.captured_at || t.uploaded_at || Date.now()).toLocaleString("fr-FR")}</div>
                <p className="mb0">{t.gpt_analysis || t.ai_summary || (t.transcription_text ? `"${t.transcription_text.slice(0, 220)}..."` : "—")}</p>
              </div>
            ))}
          </div>
        ))}
      </div>

      <LoadingOverlay show={loading} />
    </div>
  );
};

const DigestPage = () => {
  const [digest, setDigest] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiCall(`${BACKEND_URL}/api/digest`);
      setDigest(res?.digest || res || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const createNow = async () => {
    setLoading(true);
    try {
      const res = await apiCall(`${BACKEND_URL}/api/digest/create-now`, { method: "POST" });
      alert(res?.message || "Digest créé");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />

      <div className="row g8 jc-center">
        <button className="btn-primary" onClick={createNow} disabled={loading}>
          {loading ? "⏳" : "📄"} Générer maintenant
        </button>
        <a className="btn-secondary" href={`${BACKEND_URL}/api/digest/${new Date().toISOString().slice(0,10)}/pdf`} rel="noreferrer">
          📥 Télécharger le PDF du jour
        </a>
      </div>

      <div className="panel">
        <h3>Digest</h3>
        {digest ? <pre className="pre-scrollable">{JSON.stringify(digest, null, 2)}</pre> : <div className="muted">Aucun digest disponible.</div>}
      </div>

      <LoadingOverlay show={loading} />
    </div>
  );
};

const SchedulerPage = () => {
  const [status, setStatus] = useState({ jobs: [], recent_logs: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiCall(`${BACKEND_URL}/api/scheduler/status`);
      setStatus(res || {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const run = async (id) => {
    setLoading(true);
    try {
      const res = await apiCall(`${BACKEND_URL}/api/scheduler/run-job/${id}`, { method: "POST" });
      alert(res?.message || `Job ${id} exécuté`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />

      <div className="panel">
        <h3>Tâches programmées</h3>
        {(status.jobs || []).map((j) => (
          <div key={j.id} className="row g8 ai-center jc-between card-line">
            <div>
              <div className="bold">{j.name}</div>
              <div className="muted small">Prochaine exécution : {j.next_run ? new Date(j.next_run).toLocaleString("fr-FR") : "—"}</div>
            </div>
            <button className="btn-primary" onClick={() => run(j.id)}>▶️ Exécuter</button>
          </div>
        ))}
      </div>

      {status.recent_logs?.length > 0 && (
        <div className="panel">
          <h3>Logs récents</h3>
          <div className="list-compact">
            {status.recent_logs.map((l, i) => (
              <div key={i} className={cls("log-line", l.success ? "ok" : "ko")}> 
                <div className="bold">{l.job_name}</div>
                <div className="muted small">{new Date(l.timestamp).toLocaleString("fr-FR")}</div>
                {l.details && <div className="mt4">{l.details}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <LoadingOverlay show={loading} />
    </div>
  );
};

const SearchPage = () => {
  const [q, setQ] = useState("");
  const [suggest, setSuggest] = useState([]);
  const [resu, setResu] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const query = async (queryStr) => {
    if (!queryStr || queryStr.trim().length < 2) return;
    setLoading(true);
    setError("");
    try {
      const r = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(queryStr)}`);
      setResu(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadSuggest = async (text = "") => {
    try {
      const r = await apiCall(`${BACKEND_URL}/api/search/suggestions?q=${encodeURIComponent(text)}`);
      setSuggest(r?.suggestions || []);
    } catch (_) {}
  };

  useEffect(() => { loadSuggest(""); }, []);

  return (
    <div className="stack v16">
      <ErrorBanner error={error} onClose={() => setError("")} />

      <div className="row g8">
        <input
          className="glass-input fx1"
          placeholder="Rechercher (articles + réseaux sociaux)"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            if (e.target.value.length >= 2) loadSuggest(e.target.value);
          }}
          onKeyDown={(e) => e.key === "Enter" && query(q)}
        />
        <button className="btn-primary" onClick={() => query(q)} disabled={loading}>
          {loading ? "⏳" : "🔍"}
        </button>
      </div>

      {suggest.length > 0 && q.length >= 2 && (
        <div className="suggest-panel">
          {suggest.map((s, i) => (
            <button key={i} className="suggest-item" onClick={() => { setQ(s); query(s); }}>
              🔎 {s}
            </button>
          ))}
        </div>
      )}

      {resu && (
        <div className="stack v12">
          <div className="panel">
            <strong>{resu.total_results}</strong> résultats pour <em>“{resu.query}”</em>
            <div className="muted small">Sources : {(resu.searched_in || []).join(", ")}</div>
          </div>

          {resu.articles?.length > 0 && (
            <div className="panel">
              <h3>📰 Articles ({resu.articles.length})</h3>
              <div className="list">
                {resu.articles.map((a, i) => (
                  <article key={i} className="article-card">
                    <div className="article-head">
                      <SourceLogo source={a.source} />
                      <div className="fx1">
                        <a href={a.url} target="_blank" rel="noreferrer" className="article-title">
                          {a.title}
                        </a>
                        <div className="muted small">{a.source} • {new Date(a.scraped_at || Date.now()).toLocaleDateString("fr-FR")}</div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {resu.social_posts?.length > 0 && (
            <div className="panel">
              <h3>📱 Réseaux sociaux ({resu.social_posts.length})</h3>
              <div className="list">
                {resu.social_posts.map((p, i) => (
                  <div key={i} className="comment-card">
                    <div className="row g8 ai-center jc-between">
                      <div className="row g8 ai-center">
                        <SourceLogo source={p.platform || "Social"} />
                        <strong>@{p.author}</strong>
                      </div>
                      <span className="muted small">{new Date(p.created_at || Date.now()).toLocaleDateString("fr-FR")}</span>
                    </div>
                    <p className="mb0">{p.content}</p>
                    <div className="muted small mt8">❤️ {p.engagement?.total || 0}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <LoadingOverlay show={loading} />
    </div>
  );
};

/*************************************************
 * PRIVATE APP (tabs inside a protected route)
 *************************************************/
const PrivateApp = () => {
  const [tab, setTab] = useState("dashboard");

  return (
    <Shell activeTab={tab} onTabChange={setTab}>
      {tab === "dashboard" && <DashboardPage />}
      {tab === "search" && <SearchPage />}
      {tab === "articles" && <ArticlesPage />}
      {tab === "analytics" && <AnalyticsPage />}
      {tab === "sentiment" && <SentimentPage />}
      {tab === "comments" && <CommentsPage />}
      {tab === "transcription" && <TranscriptionPage />}
      {tab === "digest" && <DigestPage />}
      {tab === "scheduler" && <SchedulerPage />}
    </Shell>
  );
};

/*************************************************
 * ROOT APP WITH ROUTER + AUTH
 *************************************************/
function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <PrivateApp />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
