// src/pages/Transcriptions.jsx
import React, { useEffect, useMemo, useState } from "react";
import TranscriptionCard from "../components/TranscriptionCard";
import { api } from "../api"; // <-- ton helper existant

function normalizeTranscriptions(resp) {
  if (Array.isArray(resp)) return resp;
  const candidates = ["items", "transcriptions", "data", "result", "list"];
  for (const k of candidates) if (Array.isArray(resp?.[k])) return resp[k];
  const firstArray = Object.values(resp || {}).find((v) => Array.isArray(v));
  return Array.isArray(firstArray) ? firstArray : [];
}

export default function Transcriptions() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [sections, setSections] = useState([]);
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState("");

  async function load() {
    setLoading(true);
    setErr("");
    try {
      const [res, sec] = await Promise.all([
        api.get("/transcriptions"),
        api.get("/transcriptions/sections").catch(() => ({ sections: {} })),
      ]);
      setItems(normalizeTranscriptions(res));
      const sectList = Object.keys(sec?.sections || {});
      setSections(sectList);
    } catch (e) {
      setErr(e?.message || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((i) => (i.section || i.stream_key || "").toLowerCase() === filter.toLowerCase());
  }, [items, filter]);

  async function captureNow() {
    const section = prompt("Section à capturer (ex: rci_0620, gp_radio_0615, gp_tv_1930) :");
    if (!section) return;
    try {
      await api.post("/transcriptions/capture-now", { section, duration: 180 });
      alert("Capture lancée ✔︎");
    } catch (e) {
      alert("Échec capture: " + (e?.message || "inconnue"));
    }
  }

  const today = new Date().toISOString().slice(0, 10);
  const pdfHref = `/api/digest/${today}/pdf`;

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>Transcriptions radio / TV</h2>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #E5E7EB" }}
          >
            <option value="all">Toutes les sections</option>
            {sections.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            onClick={load}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #E5E7EB",
              background: "white",
              cursor: "pointer",
            }}
          >
            Recharger
          </button>
          <button
            onClick={captureNow}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #177670",
              background: "#177670",
              color: "white",
              cursor: "pointer",
            }}
            title="Lancer une capture immédiate (backend)"
          >
            + Capture maintenant
          </button>
          <a
            href={pdfHref}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #E5E7EB",
              background: "white",
              textDecoration: "none",
            }}
            title="PDF du digest du jour"
          >
            📄 PDF Digest (aujourd’hui)
          </a>
        </div>
      </div>

      {err ? (
        <div style={{ color: "#B91C1C", marginBottom: 12 }}>Erreur : {err}</div>
      ) : null}

      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ height: 180, background: "#F3F4F6", borderRadius: 12 }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ color: "#6B7280" }}>Aucune transcription.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
          {filtered.map((it, idx) => (
            <TranscriptionCard key={it.id || it._id || idx} item={it} />
          ))}
        </div>
      )}
    </div>
  );
}
