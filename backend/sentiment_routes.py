import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import json
import hashlib

from .async_sentiment_service import (
    analyze_text_async,
    get_text_sentiment_cached,
    get_sentiment_analysis_status,
)

logger = logging.getLogger("sentiment_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 sentiment_routes module loaded")

router = APIRouter()

# Essai d'import de l'analyseur local pour un score réel
try:
    from .sentiment_analysis_service import analyze_text_sentiment as local_analyze_sentiment  # type: ignore
except Exception:  # pragma: no cover
    local_analyze_sentiment = None


# Essai d'import du prédicteur de réaction population locale (si dispo)
try:
    from .sentiment_analysis_service import predict_population_reaction as local_predict_population_reaction  # type: ignore
except Exception:  # pragma: no cover
    local_predict_population_reaction = None

# Essai d'import du prédicteur GPT (comparaison historique)
try:
    from .gpt_sentiment_service import predict_population_reaction as gpt_predict_population_reaction  # type: ignore
except Exception:  # pragma: no cover
    gpt_predict_population_reaction = None

# ---------- Schemas ----------
class AnalyzePayload(BaseModel):
    text: str
    async_: bool = Field(False, alias="async")  # le front envoie "async"

class AnalyzeWithFrontendPayload(BaseModel):
    text: str
    frontend_snapshot: Optional[Dict[str, Any]] = None
    async_: bool = Field(False, alias="async")  # cohérent avec AnalyzePayload
    force: bool = False  # bypass cache si nécessaire

class PredictPayload(BaseModel):
    text: str
    context: Optional[Dict[str, Any]] = None
    frontend_snapshot: Optional[Dict[str, Any]] = None
    history_limit: int = 150  # nombre d'articles historiques à considérer (150 derniers)

# ---------- Petit heuristique pour /predict-reaction ----------
POS = {
    "bien","super","excellent","positif","gagne","succès","bon",
    "satisfait","favorable","bravo","fiers","fières"
}
NEG = {
    "mauvais","horrible","négatif","perdu","échec","scandale",
    "colère","triste","grave","crise","tendu","polémique"
}

def quick_predict(text: str) -> Dict[str, Any]:
    import re
    tokens = re.findall(r"\w+", (text or "").lower())
    pos = sum(t in POS for t in tokens)
    neg = sum(t in NEG for t in tokens)
    if pos > neg:
        overall, risk = "favorable", "low"
    elif neg > pos:
        overall, risk = "tendu", "high"
    else:
        overall, risk = "mitigé", "medium"
    conf = min(0.95, 0.55 + abs(pos - neg) / (pos + neg + 1))
    return {
        "overall_reaction": overall,
        "risk_level": risk,
        "likely_discussion_channels": ["Facebook", "X/Twitter", "Commentaires médias"],
        "confidence": round(conf, 2),
        "reasoning": "Heuristique simple (démo).",
    }

# ---------- Helper pour le schéma front ----------
def _map_prediction_to_front(pred: Dict[str, Any]) -> Dict[str, Any]:
    """Mappe la sortie de quick_predict (ou d'un modèle) vers le schéma attendu par le front."""
    overall = pred.get("overall_reaction", "neutre")
    # Harmoniser les libellés FR si nécessaire
    if overall in {"favorable", "positif", "positive"}: overall = "positive"
    if overall in {"tendu", "négatif", "negative"}: overall = "négative"
    risk = pred.get("risk_level", "medium")
    conf = float(pred.get("confidence", 0))
    return {
        "population_reaction": {
            "overall_reaction": overall,
            "overall_score": pred.get("overall_score", 0),  # optionnel si dispo
            "polarization_risk": {"low": "faible", "medium": "modéré", "high": "élevé"}.get(risk, "modéré"),
            "by_demographic": pred.get("by_demographic", {}),
        },
        "confidence": conf,
        "data_sources": pred.get("data_sources", {"similar_articles": 0, "similar_social_posts": 0}),
        "strategic_recommendations": pred.get("strategic_recommendations", []),
    }

# ---------- Fingerprint du snapshot pour clé de cache composite ----------

def _snapshot_fingerprint(snap: Optional[Dict[str, Any]]) -> str:
    """Crée une empreinte stable (md5 hex) du snapshot front pour casser le cache quand il change."""
    if not isinstance(snap, dict):
        return ""
    try:
        totals = snap.get("totals") or {}
        sc = snap.get("source_chart") or snap.get("sourceChart") or {}
        tl = snap.get("timeline_chart") or snap.get("timelineChart") or {}
        src_labels = sc.get("labels") or []
        tl_labels = tl.get("labels") or []
        basis = {
            "articles": int(totals.get("articles_count") or 0),
            "sources": int(totals.get("distinct_sources_count") or 0),
            "src_labels": list(map(str, src_labels))[:100],
            "tl_labels": list(map(str, tl_labels))[:365],
            "version": snap.get("snapshot_version") or 1,
        }
        raw = json.dumps(basis, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()
    except Exception:
        return ""

# ---------- Alerting (rule-based minimal) ----------
ALERT_THRESHOLDS = {
    "critical": {"score": -0.50, "confidence": 0.55},
    "high":     {"score": -0.35, "confidence": 0.50},
    "medium":   {"score": -0.20, "confidence": 0.45},
}

ALERT_ACTIONS = {
    "critical": [
        "Activer cellule de crise (porte-parole désigné).",
        "Publier un message d'empathie + faits vérifiés dans l'heure.",
        "Programmer un point presse / Q&A modéré.",
    ],
    "high": [
        "Répondre publiquement avec éléments factuels.",
        "Mobiliser relais (assos, partenaires) pour relayer la clarification.",
        "Préparer FAQ courte pour réseaux sociaux.",
    ],
    "medium": [
        "Surveiller l'évolution pendant 24h (veille renforcée).",
        "Répondre aux commentaires les plus influents.",
    ],
    "low": [
        "Monitorer sans action immédiate.",
    ],
}

def _assess_alert_level(score: float, confidence: float, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Retourne un dict { level, reasons[], actions[] } basé sur score ([-1,1]), confiance [0,1],
    et la qualité du snapshot. Règles revisitées pour mieux escalader quand le score est très négatif
    mais la confiance modérée, si le snapshot est jugé "bon" (≥3 sources et ≥2 jours).
    """
    level = "low"
    reasons = []

    # Qualité du snapshot (par défaut: inconnue)
    good_snapshot = False
    poor_snapshot = False
    try:
        if snapshot and isinstance(snapshot, dict):
            totals = snapshot.get("totals") or {}
            distinct = int(totals.get("distinct_sources_count") or 0)
            tl = snapshot.get("timeline_chart") or snapshot.get("timelineChart") or {}
            tl_labels = (tl.get("labels") if isinstance(tl, dict) else []) or []
            good_snapshot = (distinct >= 3 and len(tl_labels) >= 2)
            poor_snapshot = (distinct <= 1 and len(tl_labels) <= 1)
    except Exception:
        pass

    # Règles principales basées sur score/confidence
    if score <= ALERT_THRESHOLDS["critical"]["score"] and confidence >= ALERT_THRESHOLDS["critical"]["confidence"]:
        level = "critical"; reasons.append("Score très négatif et confiance élevée")
    elif score <= ALERT_THRESHOLDS["high"]["score"] and confidence >= ALERT_THRESHOLDS["high"]["confidence"]:
        level = "high"; reasons.append("Score négatif et confiance suffisante")
    elif score <= ALERT_THRESHOLDS["medium"]["score"] and confidence >= ALERT_THRESHOLDS["medium"]["confidence"]:
        level = "medium"; reasons.append("Score modérément négatif")

    # 🌶️ Escalade douce si snapshot jugé bon
    # Permet d'éviter un niveau trop bas quand le score est très négatif mais la confiance juste en-dessous des seuils
    if good_snapshot and level == "low":
        if score <= -0.60 and confidence >= 0.35:
            level = "high"; reasons.append("Escalade: snapshot solide et score très négatif (confiance modérée)")
        elif score <= -0.45 and confidence >= 0.30:
            level = "medium"; reasons.append("Escalade: snapshot solide et score négatif (confiance modérée)")

    # ⬇️ Déclassement si snapshot pauvre
    if poor_snapshot and level in {"critical", "high"}:
        reasons.append("Déclassement: snapshot pauvre (1 source / 1 jour)")
        level = "medium" if level == "high" else "high"

    actions = ALERT_ACTIONS.get(level, ALERT_ACTIONS["low"])
    return {"level": level, "reasons": reasons, "actions": actions}

# ---------- ENDPOINTS utilisés par le front ----------

@router.post("/sentiment/analyze", tags=["sentiment"])
async def analyze(payload: AnalyzePayload):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # On lance toujours l'analyse asynchrone et on renvoie l'ID au front
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")

    task_id = task.get("task_id") if isinstance(task, dict) else str(task)
    return {
        "success": True,
        "async": True,
        "text_hash": task_id,              # le front lit 'text_hash'
        "message": "Analyse lancée."
    }

@router.post(
    "/sentiment/analyze-with-frontend",
    tags=["sentiment"],
    operation_id="sentiment_analyze_with_frontend_v1",
)
async def analyze_with_frontend(payload: AnalyzeWithFrontendPayload):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # Lance l'analyse avec une clé de cache composite basée sur le snapshot
    fp = _snapshot_fingerprint(payload.frontend_snapshot)
    try:
        task = analyze_text_async(text, cache_key_suffix=fp, force=bool(payload.force))
    except TypeError:
        # compat ancienne signature: retombe sur la version simple
        task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")

    task_id = task.get("task_id") if isinstance(task, dict) else str(task)

    # Résume le snapshot pour logs/retour front (facultatif)
    summary = None
    snap = payload.frontend_snapshot or {}
    if isinstance(snap, dict):
        try:
            totals = snap.get("totals") or {}
            src = (snap.get("source_chart") or snap.get("sourceChart") or {})
            src_labels = (src.get("labels") if isinstance(src, dict) else []) or []
            tl = (snap.get("timeline_chart") or snap.get("timelineChart") or {})
            tl_labels = (tl.get("labels") if isinstance(tl, dict) else []) or []
            summary = {
                "articles_count": int(totals.get("articles_count") or 0),
                "distinct_sources": int(totals.get("distinct_sources_count") or 0),
                "sources_in_snapshot": len(src_labels),
                "timeline_span": len(tl_labels),
            }
        except Exception:
            summary = {"parse_error": True}

    return {
        "success": True,
        "async": True,
        "text_hash": task_id,
        "message": "Analyse lancée.",
        "snapshot_summary": summary,
        "snapshot_fp": fp,
    }

@router.get("/sentiment/status/{task_id}", tags=["sentiment"])
async def sentiment_status(task_id: str):
    status = get_sentiment_analysis_status(task_id)

    if status == "completed":
        result = get_text_sentiment_cached(task_id)
        if result:
            # IMPORTANT: le front attend { success, status: 'completed', basic_sentiment, contextual_analysis, stakeholders }
            return {"success": True, "status": "completed", **result}
        # si pas trouvé malgré 'completed'
        return {"success": True, "status": "not_found"}

    if status in ("queued", "processing"):
        return {"success": True, "status": status}

    # inconnu
    return {"success": True, "status": "not_found"}

@router.post("/sentiment/predict-reaction", tags=["sentiment"])
async def predict_reaction(payload: PredictPayload):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # Contexte fusionné: snapshot front + context appelant + contrainte d'historique (150 derniers articles)
    ctx: Dict[str, Any] = {}
    if isinstance(payload.frontend_snapshot, dict):
        ctx.update(payload.frontend_snapshot)
    if isinstance(payload.context, dict):
        ctx.update(payload.context)
    ctx.setdefault("history_limit", int(payload.history_limit or 150))
    ctx.setdefault("history_scope", "recent_articles")  # explicite: ne prendre que les plus récents

    # 1) Chemin privilégié: prédiction GPT basée sur comparaison à l'historique réduit
    if callable(globals().get("gpt_predict_population_reaction")):
        try:
            pred = gpt_predict_population_reaction(text, context=ctx)  # type: ignore
            # Mapping UI
            mapped = _map_prediction_to_front(pred)
            mapped["population_reaction"]["overall_score"] = round(float(pred.get("overall_score", 0.0) or 0.0), 3)
            mapped["confidence"] = max(0.3, min(1.0, float(pred.get("confidence", 0.0) or 0.0)))
            mapped["strategic_recommendations"] = pred.get("strategic_recommendations", [])
            mapped["alert"] = _assess_alert_level(
                float(pred.get("overall_score", 0.0) or 0.0),
                float(mapped.get("confidence", 0.5) or 0.5),
                payload.frontend_snapshot if isinstance(payload.frontend_snapshot, dict) else None,
            )
            return {"success": True, "reactionPrediction": mapped, "prediction": pred}
        except Exception as e:
            logger.warning(f"GPT predictor failed, falling back to local heuristic: {e}")

    # 2) Fallback strict (si module GPT indisponible): heuristique + local
    base_pred = quick_predict(text)
    score = 0.0
    local_conf = None
    try:
        if callable(globals().get("local_analyze_sentiment")):
            local_res = local_analyze_sentiment(text) or {}
            score = float(local_res.get("score", 0.0) or 0.0)
            details = local_res.get("analysis_details") or {}
            if isinstance(details, dict) and "confidence" in details:
                local_conf = float(details.get("confidence") or 0.0)
    except Exception:
        pass

    mapped = _map_prediction_to_front(base_pred)
    mapped["population_reaction"]["overall_score"] = round(score, 3)
    if isinstance(local_conf, float):
        mapped["confidence"] = max(0.3, min(1.0, local_conf))

    # Ajustement confiance via snapshot
    if payload.frontend_snapshot and isinstance(payload.frontend_snapshot, dict):
        try:
            totals = payload.frontend_snapshot.get("totals") or {}
            distinct = int(totals.get("distinct_sources_count") or 0)
            tl = payload.frontend_snapshot.get("timeline_chart") or payload.frontend_snapshot.get("timelineChart") or {}
            tl_labels = (tl.get("labels") if isinstance(tl, dict) else []) or []
            if distinct <= 1 and len(tl_labels) <= 1:
                mapped["confidence"] = min(mapped.get("confidence", 0.6), 0.6)
        except Exception:
            pass

    # Risque de polarisation
    a = abs(score)
    mapped["population_reaction"]["polarization_risk"] = "faible" if a < 0.15 else ("modéré" if a < 0.35 else "élevé")

    # Cohérence label vs score
    if score > 0.15 and mapped["population_reaction"]["overall_reaction"] != "positive":
        mapped["population_reaction"]["overall_reaction"] = "positive"
    elif score < -0.15 and mapped["population_reaction"]["overall_reaction"] != "négative":
        mapped["population_reaction"]["overall_reaction"] = "négative"

    mapped["alert"] = _assess_alert_level(score, float(mapped.get("confidence", 0.5)), payload.frontend_snapshot)

    recs = []
    if score <= -0.35:
        recs = [
            "Répondre vite avec un message d’empathie.",
            "Partager des faits vérifiés et des sources fiables.",
            "Proposer une action corrective concrète.",
        ]
    elif score >= 0.35:
        recs = [
            "Amplifier les retours positifs sur les réseaux.",
            "Remercier publiquement les soutiens.",
            "Transformer en témoignages / cas d’usage.",
        ]
    mapped["strategic_recommendations"] = recs

    return {"success": True, "reactionPrediction": mapped, "prediction": base_pred}

# ---------- (Optionnel) Compat: anciennes routes alignées au format attendu ----------

@router.post("/sentiment/async", tags=["sentiment"])
async def enqueue_sentiment(payload: Dict[str, Any]):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")
    task_id = task.get("task_id") if isinstance(task, dict) else str(task)
    return {"success": True, "async": True, "text_hash": task_id, "message": "Analyse en file d'attente."}

@router.get("/sentiment/result/{task_id}", tags=["sentiment"])
async def sentiment_result(task_id: str):
    result = get_text_sentiment_cached(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Résultat non disponible")
    # On renvoie aussi 'success' pour cohérence
    return {"success": True, **result}

@router.post("/sentiment/alerts/assess", tags=["sentiment"], operation_id="sentiment_alerts_assess_v1")
async def assess_alert(payload: Dict[str, Any]):
    text = (payload.get("text") or "").strip()
    snap = payload.get("frontend_snapshot")

    # Option: si un score est fourni par le front (ex: analyse locale), on l'utilise; sinon on approxime
    score = float(payload.get("score") or 0.0)
    conf = float(payload.get("confidence") or 0.5)

    if not payload.get("score") and text:
        try:
            if callable(local_analyze_sentiment):
                local_res = local_analyze_sentiment(text) or {}
                score = float(local_res.get("score", 0.0) or 0.0)
        except Exception:
            pass

    alert = _assess_alert_level(score, conf, snap)
    return {"success": True, "alert": alert, "inputs": {"score": score, "confidence": conf}}