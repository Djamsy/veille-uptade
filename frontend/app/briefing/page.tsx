"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchBriefing,
  sendBriefingTelegram,
  fetchTrending,
  fetchWatchlist,
  addWatchlistKeyword,
  removeWatchlistKeyword,
  type BriefingResponse,
  type TrendingAffair,
  type WatchlistItem,
} from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────

function gravityColor(g: number) {
  if (g >= 0.75) return "var(--negative)";
  if (g >= 0.55) return "var(--warning, #f59e0b)";
  if (g >= 0.4) return "var(--accent)";
  return "var(--positive)";
}

function gravityBadge(g: number) {
  if (g >= 0.75) return { label: "CRITIQUE", color: "var(--negative)" };
  if (g >= 0.55) return { label: "IMPORTANT", color: "var(--warning, #f59e0b)" };
  if (g >= 0.4) return { label: "À SUIVRE", color: "var(--accent)" };
  return { label: "MINEUR", color: "var(--positive)" };
}

function timeAgo(dateStr: string | undefined) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `il y a ${mins}min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `il y a ${hrs}h`;
  return `il y a ${Math.floor(hrs / 24)}j`;
}

// ── Page ───────────────────────────────────────────────────

export default function BriefingPage() {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [trending, setTrending] = useState<TrendingAffair[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hours, setHours] = useState(24);
  const [newKeyword, setNewKeyword] = useState("");
  const [newCategory, setNewCategory] = useState("general");
  const [telegramSending, setTelegramSending] = useState(false);
  const [telegramMsg, setTelegramMsg] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [bRes, tRes, wRes] = await Promise.all([
        fetchBriefing(hours),
        fetchTrending(12),
        fetchWatchlist(),
      ]);
      setBriefing(bRes);
      setTrending(tRes.trending || []);
      setWatchlist(wRes.watchlist || []);
    } catch (e: unknown) {
      setError((e as Error).message || "Erreur chargement");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSendTelegram = async () => {
    setTelegramSending(true);
    try {
      const res = await sendBriefingTelegram(hours);
      setTelegramMsg(res.message);
      setTimeout(() => setTelegramMsg(""), 3000);
    } catch {
      setTelegramMsg("Erreur envoi");
    } finally {
      setTelegramSending(false);
    }
  };

  const handleAddKeyword = async () => {
    if (!newKeyword.trim()) return;
    try {
      await addWatchlistKeyword(newKeyword.trim(), newCategory);
      setNewKeyword("");
      const wRes = await fetchWatchlist();
      setWatchlist(wRes.watchlist || []);
    } catch {
      /* ignore */
    }
  };

  const handleRemoveKeyword = async (kw: string) => {
    try {
      await removeWatchlistKeyword(kw);
      setWatchlist((prev) => prev.filter((w) => w.keyword !== kw.toLowerCase()));
    } catch {
      /* ignore */
    }
  };

  const b = briefing?.briefing;
  const stats = b?.stats;

  return (
    <div className="main-content p-3 sm:p-5 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1
            className="text-xl sm:text-2xl font-bold"
            style={{ color: "var(--text)" }}
          >
            ☀️ Briefing Veille
          </h1>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--text-muted)" }}
          >
            Résumé intelligence des dernières {hours}h
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="input-dark text-sm px-3 py-2 rounded-xl"
          >
            <option value={6}>6h</option>
            <option value={12}>12h</option>
            <option value={24}>24h</option>
            <option value={48}>48h</option>
            <option value={72}>72h</option>
          </select>
          <button
            onClick={loadData}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{
              background: "var(--primary)",
              color: "#fff",
            }}
          >
            Actualiser
          </button>
          <button
            onClick={handleSendTelegram}
            disabled={telegramSending}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{
              background: "var(--accent)",
              color: "#1a1a2e",
              opacity: telegramSending ? 0.6 : 1,
            }}
          >
            {telegramSending ? "Envoi..." : "📨 Telegram"}
          </button>
          {telegramMsg && (
            <span className="text-xs" style={{ color: "var(--positive)" }}>
              {telegramMsg}
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div
          className="text-center py-12 text-lg"
          style={{ color: "var(--text-muted)" }}
        >
          Chargement du briefing...
        </div>
      )}
      {error && (
        <div
          className="glass-card p-4 text-center"
          style={{ color: "var(--negative)" }}
        >
          {error}
        </div>
      )}

      {!loading && b && (
        <>
          {/* ── Stats overview ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Articles", value: stats?.articles_count ?? 0, icon: "📰" },
              { label: "Radio", value: stats?.radio_captures_count ?? 0, icon: "📻" },
              {
                label: "Nouvelles affaires",
                value: stats?.new_affairs_count ?? 0,
                icon: "🆕",
              },
              {
                label: "Affaires actives",
                value: stats?.total_active_affairs ?? 0,
                icon: "📋",
              },
            ].map((s) => (
              <div key={s.label} className="glass-card p-4 text-center">
                <div className="text-2xl">{s.icon}</div>
                <div
                  className="text-2xl font-bold mt-1"
                  style={{ color: "var(--primary)" }}
                >
                  {s.value}
                </div>
                <div
                  className="text-xs mt-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          {/* ── Trending ── */}
          {trending.length > 0 && (
            <section className="glass-card p-4 sm:p-5">
              <h2
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                📈 Tendances — Affaires en accélération
              </h2>
              <div className="space-y-3">
                {trending.map((t) => (
                  <div
                    key={t._id}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{
                      background: "var(--bg-elevated)",
                      borderLeft: `3px solid ${gravityColor(t.gravity_score)}`,
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <div
                        className="font-medium text-sm truncate"
                        style={{ color: "var(--text)" }}
                      >
                        {t.title}
                      </div>
                      <div
                        className="text-xs mt-1 flex items-center gap-2 flex-wrap"
                        style={{ color: "var(--text-muted)" }}
                      >
                        <span>⚡ {t.velocity} activités</span>
                        <span>📡 {t.source_spread} sources</span>
                        {t.theme && <span>🏷 {t.theme}</span>}
                        {t.is_new && (
                          <span
                            className="px-2 py-0.5 rounded-full text-xs font-medium"
                            style={{
                              background: "var(--positive)",
                              color: "#fff",
                            }}
                          >
                            NOUVEAU
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div
                        className="text-xs font-bold px-2 py-1 rounded-lg"
                        style={{
                          background: gravityColor(t.gravity_score),
                          color: "#fff",
                        }}
                      >
                        {(t.gravity_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Top affaires + Nouvelles ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Top affaires */}
            <section className="glass-card p-4 sm:p-5">
              <h2
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                🔥 Top Affaires
              </h2>
              <div className="space-y-2">
                {b.top_affairs.slice(0, 8).map((a, i) => {
                  const badge = gravityBadge(a.gravity_score);
                  return (
                    <div
                      key={a._id}
                      className="flex items-start gap-2 p-2 rounded-lg"
                      style={{ background: i < 3 ? "var(--bg-elevated)" : "transparent" }}
                    >
                      <span
                        className="text-xs font-bold shrink-0 w-5 text-center mt-0.5"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div
                          className="text-sm font-medium truncate"
                          style={{ color: "var(--text)" }}
                        >
                          {a.title}
                        </div>
                        <div
                          className="text-xs mt-0.5 flex gap-2"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <span>{a.sources?.length ?? 0} sources</span>
                          <span>{a.item_count} items</span>
                          {a.commune && <span>📍 {a.commune}</span>}
                        </div>
                      </div>
                      <span
                        className="text-xs font-bold px-2 py-0.5 rounded-lg shrink-0"
                        style={{ background: badge.color, color: "#fff" }}
                      >
                        {badge.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Nouvelles affaires */}
            <section className="glass-card p-4 sm:p-5">
              <h2
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                🆕 Nouvelles Affaires ({b.new_affairs.length})
              </h2>
              {b.new_affairs.length === 0 ? (
                <p
                  className="text-sm py-4 text-center"
                  style={{ color: "var(--text-muted)" }}
                >
                  Aucune nouvelle affaire dans la période
                </p>
              ) : (
                <div className="space-y-2">
                  {b.new_affairs.slice(0, 8).map((a) => (
                    <div
                      key={a._id}
                      className="p-3 rounded-xl"
                      style={{
                        background: "var(--bg-elevated)",
                        borderLeft: `3px solid ${gravityColor(a.gravity_score)}`,
                      }}
                    >
                      <div
                        className="text-sm font-medium truncate"
                        style={{ color: "var(--text)" }}
                      >
                        {a.title}
                      </div>
                      <div
                        className="text-xs mt-1 flex gap-2"
                        style={{ color: "var(--text-muted)" }}
                      >
                        <span
                          style={{ color: gravityColor(a.gravity_score) }}
                        >
                          {(a.gravity_score * 100).toFixed(0)}%
                        </span>
                        {a.theme && <span>🏷 {a.theme}</span>}
                        <span>{timeAgo(a.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* ── Radio highlights ── */}
          {b.radio_highlights.length > 0 && (
            <section className="glass-card p-4 sm:p-5">
              <h2
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                🎙️ Radio — Points clés
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {b.radio_highlights.slice(0, 6).map((r, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl"
                    style={{ background: "var(--bg-elevated)" }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="text-xs font-bold px-2 py-0.5 rounded-lg"
                        style={{
                          background: "var(--primary)",
                          color: "#fff",
                        }}
                      >
                        {r.stream}
                      </span>
                      {r.gravity > 0 && (
                        <span
                          className="text-xs"
                          style={{ color: gravityColor(r.gravity) }}
                        >
                          {(r.gravity * 100).toFixed(0)}%
                        </span>
                      )}
                      <span
                        className="text-xs ml-auto"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {timeAgo(r.captured_at)}
                      </span>
                    </div>
                    {r.topic && (
                      <div
                        className="text-xs font-medium mb-1"
                        style={{ color: "var(--accent)" }}
                      >
                        {r.topic}
                      </div>
                    )}
                    <p
                      className="text-xs leading-relaxed"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {r.summary.slice(0, 200)}
                      {r.summary.length > 200 && "..."}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Coverage gaps ── */}
          {b.coverage.coverage_gaps.length > 0 && (
            <section className="glass-card p-4 sm:p-5">
              <h2
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                ⚠️ Trous de couverture
              </h2>
              <p
                className="text-xs mb-3"
                style={{ color: "var(--text-muted)" }}
              >
                Affaires graves couvertes par une seule source
              </p>
              <div className="space-y-2">
                {b.coverage.coverage_gaps.map((g, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 p-3 rounded-xl"
                    style={{ background: "var(--bg-elevated)" }}
                  >
                    <div className="flex-1 min-w-0">
                      <div
                        className="text-sm font-medium truncate"
                        style={{ color: "var(--text)" }}
                      >
                        {g.affair_title}
                      </div>
                      <div
                        className="text-xs mt-1"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Couvert par : {g.covered_by.join(", ") || "aucune"} •
                        Absent de : {g.missing_from.join(", ")}
                      </div>
                    </div>
                    <span
                      className="text-xs font-bold px-2 py-1 rounded-lg shrink-0"
                      style={{
                        background: gravityColor(g.gravity),
                        color: "#fff",
                      }}
                    >
                      {(g.gravity * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Watchlist ── */}
          <section className="glass-card p-4 sm:p-5">
            <h2
              className="text-lg font-semibold mb-3"
              style={{ color: "var(--text)" }}
            >
              🔔 Watchlist — Mots-clés surveillés
            </h2>

            {/* Add form */}
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <input
                type="text"
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
                placeholder="Nouveau mot-clé..."
                className="input-dark text-sm px-3 py-2 rounded-xl flex-1 min-w-[150px]"
                onKeyDown={(e) => e.key === "Enter" && handleAddKeyword()}
              />
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="input-dark text-sm px-3 py-2 rounded-xl"
              >
                <option value="general">Général</option>
                <option value="politique">Politique</option>
                <option value="environnement">Environnement</option>
                <option value="securite">Sécurité</option>
                <option value="personnalite">Personnalité</option>
                <option value="institution">Institution</option>
              </select>
              <button
                onClick={handleAddKeyword}
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: "var(--positive)", color: "#fff" }}
              >
                + Ajouter
              </button>
            </div>

            {/* Watchlist items */}
            {watchlist.length === 0 ? (
              <p
                className="text-sm text-center py-3"
                style={{ color: "var(--text-muted)" }}
              >
                Aucun mot-clé surveillé. Ajoutez-en pour recevoir des alertes.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {watchlist.map((w) => (
                  <div
                    key={w._id}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm"
                    style={{ background: "var(--bg-elevated)" }}
                  >
                    <span style={{ color: "var(--text)" }}>
                      {w.keyword_display}
                    </span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--primary)",
                        color: "#fff",
                        opacity: 0.8,
                      }}
                    >
                      {w.category}
                    </span>
                    {w.hit_count > 0 && (
                      <span
                        className="text-xs"
                        style={{ color: "var(--accent)" }}
                      >
                        {w.hit_count}×
                      </span>
                    )}
                    <button
                      onClick={() => handleRemoveKeyword(w.keyword)}
                      className="text-xs ml-1 hover:opacity-100 opacity-60 transition-opacity"
                      style={{ color: "var(--negative)" }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Watchlist hits */}
            {b.watchlist_hits.length > 0 && (
              <div className="mt-4 space-y-2">
                <h3
                  className="text-sm font-semibold"
                  style={{ color: "var(--accent)" }}
                >
                  Alertes récentes
                </h3>
                {b.watchlist_hits.map((h, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl"
                    style={{
                      background: "var(--bg-elevated)",
                      borderLeft: "3px solid var(--accent)",
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="font-medium text-sm"
                        style={{ color: "var(--text)" }}
                      >
                        🏷 {h.keyword}
                      </span>
                      <span
                        className="text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {h.articles_matched} articles, {h.radio_matched} radio
                      </span>
                    </div>
                    {h.top_articles.length > 0 && (
                      <div className="mt-1">
                        {h.top_articles.slice(0, 2).map((a, j) => (
                          <div
                            key={j}
                            className="text-xs truncate"
                            style={{ color: "var(--text-secondary)" }}
                          >
                            📰 {a.title} ({a.source})
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Distribution thèmes + sentiments ── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <section className="glass-card p-4">
              <h3
                className="text-sm font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                🏷 Répartition thématique
              </h3>
              <div className="space-y-1.5">
                {Object.entries(stats?.themes_distribution ?? {})
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .slice(0, 8)
                  .map(([theme, count]) => {
                    const max = Math.max(
                      ...Object.values(stats?.themes_distribution ?? {}).map(Number)
                    );
                    const pct = max > 0 ? ((count as number) / max) * 100 : 0;
                    return (
                      <div key={theme} className="flex items-center gap-2">
                        <span
                          className="text-xs w-24 truncate"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {theme}
                        </span>
                        <div
                          className="flex-1 h-4 rounded-full overflow-hidden"
                          style={{ background: "var(--bg-elevated)" }}
                        >
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${pct}%`,
                              background: "var(--primary)",
                              opacity: 0.8,
                            }}
                          />
                        </div>
                        <span
                          className="text-xs w-6 text-right"
                          style={{ color: "var(--text)" }}
                        >
                          {count as number}
                        </span>
                      </div>
                    );
                  })}
              </div>
            </section>

            <section className="glass-card p-4">
              <h3
                className="text-sm font-semibold mb-3"
                style={{ color: "var(--text)" }}
              >
                📡 Sources actives
              </h3>
              <div className="space-y-1.5">
                {Object.entries(stats?.sources_active ?? {})
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .map(([source, count]) => (
                    <div
                      key={source}
                      className="flex items-center justify-between text-sm px-2 py-1 rounded-lg"
                      style={{ background: "var(--bg-elevated)" }}
                    >
                      <span style={{ color: "var(--text)" }}>{source}</span>
                      <span
                        className="font-bold"
                        style={{ color: "var(--primary)" }}
                      >
                        {count as number}
                      </span>
                    </div>
                  ))}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
