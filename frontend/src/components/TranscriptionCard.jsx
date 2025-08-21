// src/components/TranscriptionCard.jsx
import React from "react";

const BRAND = {
  primary: "#177670",
  accent: "#F8B902",
  border: "#E5E7EB",
  text: "#202C38",
  muted: "#6B7280",
  chip: "#F8FAFC",
};

function fmtDate(dt) {
  try {
    const d = new Date(dt);
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return dt || "";
  }
}

export default function TranscriptionCard({ item = {} }) {
  const name = item.stream_name || item.section || "Transcription";
  const when = fmtDate(item.captured_at || item.timestamp);
  const dur = item.duration_seconds ? Math.round(item.duration_seconds / 60) + " min" : "";
  const summary = item.ai_summary || item.gpt_analysis || item.transcription_text || "";
  const section = item.section || item.stream_key || "";

  return (
    <div
      style={{
        border: `1px solid ${BRAND.border}`,
        borderRadius: 12,
        background: "white",
        boxShadow: "0 1px 2px rgba(16,24,40,0.05)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          height: 4,
          background: `linear-gradient(90deg, ${BRAND.primary} 0%, ${BRAND.accent} 50%, ${BRAND.primary} 100%)`,
        }}
      />
      <div style={{ padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
          {section ? (
            <div
              style={{
                padding: "4px 10px",
                background: BRAND.chip,
                border: `1px solid ${BRAND.border}`,
                borderRadius: 999,
                fontSize: 12,
                color: BRAND.muted,
              }}
              title="Section"
            >
              {section}
            </div>
          ) : null}
          {dur ? (
            <div
              style={{
                padding: "4px 10px",
                background: BRAND.chip,
                border: `1px solid ${BRAND.border}`,
                borderRadius: 999,
                fontSize: 12,
                color: BRAND.muted,
              }}
              title="Durée"
            >
              ⏱ {dur}
            </div>
          ) : null}
        </div>

        <h3 style={{ margin: "4px 0 6px", color: BRAND.text, fontSize: 16 }}>{name}</h3>
        <div style={{ color: BRAND.muted, fontSize: 12, marginBottom: 10 }}>📅 {when}</div>

        <p style={{ color: BRAND.text, fontSize: 14, lineHeight: 1.45, margin: 0 }}>
          {summary?.length > 800 ? summary.slice(0, 800) + "…" : summary || "—"}
        </p>
      </div>
    </div>
  );
}
