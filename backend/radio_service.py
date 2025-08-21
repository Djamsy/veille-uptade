# backend/radio_service.py
"""
Service de capture & transcription des flux (radio/TV) Guadeloupe.
- Schedules locaux (America/Guadeloupe) avec adaptation UTC
- Capture réelle via FFmpeg (URL directes ou pages résolues via streamlink)
- Transcription Whisper API (OpenAI) + fallback résumé local
- Capture segmentée auto si > 10 min
- Dédup minute (évite double exécution si job lancé 2x la même minute)
"""

import os
import re
import shutil
import time
import logging
import tempfile
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from zoneinfo import ZoneInfo

from pymongo import MongoClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ==========
# ENV & TZ
# ==========
TIMEZONE_NAME = os.environ.get("TIMEZONE", "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TZ = ZoneInfo("UTC")
    TIMEZONE_NAME = "UTC"
    logger.warning("TIMEZONE invalide, fallback UTC")

# FFmpeg & headers
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")
DEFAULT_UA = os.environ.get(
    "FFMPEG_UA",
    "Mozilla/5.0 (compatible; VeilleRadio/1.0; +https://example.local)"
)
LA1ERE_REFERER = "https://la1ere.franceinfo.fr/"


def _resolve_ffmpeg_bin():
    """Assure la présence d'un binaire ffmpeg utilisable."""
    global FFMPEG_BIN
    try:
        if not os.path.exists(FFMPEG_BIN):
            alt = shutil.which("ffmpeg")
            if alt:
                FFMPEG_BIN = alt
                logger.info(f"⚙️ FFmpeg détecté via PATH: {FFMPEG_BIN}")
            else:
                logger.error("❌ FFmpeg introuvable. Définissez FFMPEG_BIN ou installez ffmpeg.")
    except Exception as e:
        logger.warning(f"⚠️ Vérification FFMPEG_BIN: {e}")


# =========================
# Service principal
# =========================
class RadioTranscriptionService:
    """
    Les créneaux demandés :

    - Lundi 18:30–19:00 : Direct TV Guadeloupe La 1ère (30 min)
    - Lundi→Vendredi 06:15 (9 min) : Radio Guadeloupe La 1ère
    - Lundi→Vendredi 06:20 (15 min) : RCI Guadeloupe
    - Variante : TV 19:30 (30 min) Guadeloupe La 1ère (tous les jours)

    On stocke tout en local TZ puis conversion si besoin.
    Un scheduler (à part) appellera capture_due_streams() chaque minute.
    """

    def __init__(self):
        # Mongo
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.transcriptions_collection = self.db.radio_transcriptions

        _resolve_ffmpeg_bin()

        # ---------- Définition des flux + schedules locaux ----------
        # days: mon,tue,wed,thu,fri,sat,sun  (helper accepte 'weekdays','weekends','daily')
        # hour/minute: heure locale Guadeloupe
        self.streams: Dict[str, Dict[str, Any]] = {
            # Radio RCI à 06:20 (lun→ven) 15 min
            "rci_0620": {
                "name": "RCI 6h20",
                "section": "RCI 6h20",
                "description": "RCI Guadeloupe - tranche matinale",
                "type": "radio",
                "url": "http://n01a-eu.rcs.revma.com/v4hf7bwspwzuv?rj-ttl=5&rj-tok=AAABmFgYf1YAGI3rfz2-KTLPnA",
                "duration_minutes": 15,
                "schedule": {"days": "weekdays", "hour": 6, "minute": 20},
                "priority": 1,
            },
            # Radio Guadeloupe 1ère à 06:15 (lun→ven) 9 min
            "gp_radio_0615": {
                "name": "Guadeloupe 1ère Radio 6h15",
                "section": "GP Radio 6h15",
                "description": "Guadeloupe 1ère - actualités matinales",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 9,
                "schedule": {"days": "weekdays", "hour": 6, "minute": 15},
                "priority": 2,
            },
            # TV Guadeloupe 1ère Lundi 18:30 (30 min)
            "gp_tv_lundi_1830": {
                "name": "Guadeloupe 1ère TV (Lundi 18h30)",
                "section": "GP TV 18h30 (Lundi)",
                "description": "Direct TV - Guadeloupe La 1ère",
                "type": "tv",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/direct-tv.html",
                "duration_minutes": 30,
                "schedule": {"days": ["mon"], "hour": 18, "minute": 30},
                "priority": 3,
            },
            # Variante : TV 19:30 (tous les jours) 30 min
            "gp_tv_1930": {
                "name": "Guadeloupe 1ère TV 19h30",
                "section": "GP TV 19h30",
                "description": "Journal TV 19h30 - Direct TV",
                "type": "tv",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/direct-tv.html",
                "duration_minutes": 30,
                "schedule": {"days": "daily", "hour": 19, "minute": 30},
                "priority": 4,
            },
            # (Compat ancien) 7h RCI / 7h GP si tu veux les garder :
            "rci_7h": {
                "name": "7H RCI",
                "section": "7H RCI",
                "description": "RCI Guadeloupe - Journal matinal",
                "type": "radio",
                "url": "http://n01a-eu.rcs.revma.com/v4hf7bwspwzuv?rj-ttl=5&rj-tok=AAABmFgYf1YAGI3rfz2-KTLPnA",
                "duration_minutes": 20,
                "schedule": {"days": "daily", "hour": 7, "minute": 0},
                "priority": 9,
            },
            "guadeloupe_premiere_7h": {
                "name": "7H Guadeloupe Première",
                "section": "7H Guadeloupe Première",
                "description": "Guadeloupe Première - Actualités matinales",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 30,
                "schedule": {"days": "daily", "hour": 7, "minute": 0},
                "priority": 10,
            },
        }

        # Statut UI par flux
        self.status: Dict[str, Dict[str, Any]] = {
            key: {
                "in_progress": False,
                "current_step": "idle",
                "step_details": "",
                "started_at": None,
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None,
            }
            for key in self.streams
        }

        # Dédup exécution (clé = "YYYY-MM-DD HH:MM")
        self._last_run_minute: Dict[str, str] = {}

        self.cleanup_stale_status()

    # -------------
    # Helpers TZ & schedule
    # -------------
    @staticmethod
    def _dow_tag(dt_local: datetime) -> str:
        return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt_local.weekday()]

    @staticmethod
    def _expand_days(days: Any) -> List[str]:
        if not days or days == "daily":
            return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        if days == "weekdays":
            return ["mon", "tue", "wed", "thu", "fri"]
        if days == "weekends":
            return ["sat", "sun"]
        if isinstance(days, str):
            return [d.strip().lower() for d in re.split(r"[,\s]+", days) if d.strip()]
        return [d.strip().lower() for d in days]

    def _now_pair(self, now_utc: Optional[datetime] = None) -> Dict[str, datetime]:
        if now_utc is None:
            now_utc = datetime.now(ZoneInfo("UTC"))
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
        return {"utc": now_utc, "local": now_utc.astimezone(TZ)}

    def _is_due_now(self, cfg: Dict[str, Any], now_local: datetime, window_min: int = 2) -> bool:
        sch = cfg.get("schedule") or {}
        days = set(self._expand_days(sch.get("days")))
        if self._dow_tag(now_local) not in days:
            return False

        hour = int(sch.get("hour", cfg.get("start_hour", 0)))
        minute = int(sch.get("minute", cfg.get("start_minute", 0)))

        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = abs((now_local - target).total_seconds()) / 60.0
        return delta < max(1, window_min)

    # =========================
    # Résolution d'URL (TV/Radio)
    # =========================
    def resolve_input_url(self, url: str) -> str:
        try:
            lowered = (url or "").lower()
            if lowered.endswith((".mp3", ".m3u8")):
                return url

            try:
                from streamlink import Streamlink  # type: ignore
                session = Streamlink()
                streams = session.streams(url)
                if streams:
                    stream = streams.get("best") or next(iter(streams.values()))
                    real_url = None
                    if hasattr(stream, "to_url"):
                        try:
                            real_url = stream.to_url()  # type: ignore[attr-defined]
                        except Exception:
                            real_url = None
                    if not real_url:
                        real_url = getattr(stream, "url", None)
                    if isinstance(real_url, str) and real_url:
                        for prefix in ("hlsvariant://", "hls://"):
                            if real_url.startswith(prefix):
                                real_url = real_url[len(prefix):]
                        logger.info(f"🎯 URL résolue via streamlink: {real_url}")
                        return real_url
            except Exception as e:
                logger.debug(f"Streamlink API KO: {e}")

            # Fallback CLI
            try:
                proc = subprocess.run(
                    ["streamlink", "--stream-url", url, "best"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                out = (proc.stdout or "").strip()
                if proc.returncode == 0 and out:
                    logger.info(f"🎯 URL résolue via streamlink CLI: {out}")
                    return out
                else:
                    logger.debug(f"streamlink CLI échec (rc={proc.returncode}): {proc.stderr}")
            except Exception as e:
                logger.debug(f"streamlink CLI KO: {e}")
        except Exception as e:
            logger.warning(f"resolve_input_url: {e}")
        return url

    # =========================
    # Statut
    # =========================
    def _update_step(self, key: str, step: str, details: str = "", progress: int = 0):
        if key not in self.status:
            return
        st = self.status[key]
        st["current_step"] = step
        st["step_details"] = details
        st["progress_percentage"] = progress
        st["last_update"] = datetime.now(TZ).isoformat()

        if step == "audio_capture" and not st["in_progress"]:
            st["in_progress"] = True
            st["started_at"] = datetime.now(TZ).isoformat()
            st["cache_expires_at"] = (datetime.now(TZ) + timedelta(hours=24)).isoformat()

        if step in ("completed", "error"):
            st["in_progress"] = False
            st["estimated_completion"] = None
            if step == "completed":
                st["progress_percentage"] = 100

        logger.info(f"🔄 {self.streams[key]['name']}: {step} - {details} ({progress}%)")

    def cleanup_stale_status(self):
        now = datetime.now(TZ)
        for key, st in self.status.items():
            if st["in_progress"] and st.get("started_at"):
                try:
                    started = datetime.fromisoformat(st["started_at"])
                    if (now - started) > timedelta(hours=2):
                        self._update_step(key, "error", "Statut expiré - reset", 0)
                except Exception:
                    self._update_step(key, "idle", "Réinitialisé", 0)

    # =========================
    # Capture
    # =========================
    def _ffmpeg_capture(self, input_url: str, duration_seconds: int, origin_url_for_headers: str) -> Optional[str]:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            out_path = tmp.name

        headers_args: List[str] = []
        if "la1ere.franceinfo.fr" in (input_url or origin_url_for_headers or ""):
            headers_args = ["-headers", f"Referer: {LA1ERE_REFERER}\r\n"]

        cmd = [
            FFMPEG_BIN, "-hide_banner", "-loglevel", "warning",
            "-user_agent", DEFAULT_UA,
            *headers_args,
            "-i", input_url,
            "-t", str(duration_seconds),
            "-acodec", "mp3", "-ar", "16000", "-ac", "1",
            "-y", out_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=duration_seconds + 45, check=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                return out_path
        except subprocess.TimeoutExpired:
            logger.error("Timeout ffmpeg")
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error: {e}")
        except Exception as e:
            logger.error(f"ffmpeg unexpected: {e}")

        if os.path.exists(out_path):
            os.unlink(out_path)
        return None

    def capture_radio_stream(self, key: str, duration_seconds: int) -> Optional[str]:
        cfg = self.streams[key]
        self._update_step(key, "audio_capture", f"Capture ({duration_seconds}s)", 10)
        logger.info(f"🎵 Capture {cfg['name']} pendant {duration_seconds}s")

        input_url = self.resolve_input_url(cfg["url"])
        path = self._ffmpeg_capture(input_url, duration_seconds, cfg["url"])
        if path:
            size = os.path.getsize(path)
            self._update_step(key, "transcription", f"Audio capturé ({size/1024:.1f} KB)", 40)
            logger.info(f"✅ Audio capturé: {size} bytes")
            return path

        self._update_step(key, "error", "Échec capture", 0)
        return None

    # =========================
    # Transcription & fusion
    # =========================
    def transcribe_audio_file(self, audio_path: str, key: str = "unknown") -> Optional[Dict[str, Any]]:
        try:
            if key != "unknown":
                self._update_step(key, "transcription", "Transcription Whisper…", 60)

            try:
                from backend.gpt_analysis_service import gpt_analyzer
            except Exception:
                from gpt_analysis_service import gpt_analyzer  # fallback

            if not getattr(gpt_analyzer, "client", None):
                raise RuntimeError("Client OpenAI indisponible")

            with open(audio_path, "rb") as f:
                transcript = gpt_analyzer.client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="fr"
                )

            data = {
                "text": (transcript.text or "").strip(),
                "language": "fr",
                "segments": [],
                "duration": 0,
                "method": "openai_whisper_api",
            }
            if key != "unknown":
                self._update_step(key, "gpt_analysis", f"Transcription OK ({len(data['text'])} chars)", 70)
            return data
        except Exception as e:
            logger.error(f"Transcription erreur: {e}")
            if key != "unknown":
                self._update_step(key, "error", f"Transcription: {e}", 0)
            return None

    # =========================
    # Pipeline complet
    # =========================
    def capture_and_transcribe_stream(self, key: str, duration_override_secs: Optional[int] = None) -> Dict[str, Any]:
        cfg = self.streams[key]
        duration_seconds = duration_override_secs or int(cfg["duration_minutes"]) * 60

        result: Dict[str, Any] = {
            "success": False,
            "stream_key": key,
            "stream_name": cfg["name"],
            "section": cfg["section"],
            "timestamp": datetime.now(TZ).isoformat(),
            "error": None,
            "transcription": None,
        }

        path = None
        try:
            path = self.capture_radio_stream(key, duration_seconds)
            if not path:
                result["error"] = "Capture audio: échec"
                return result

            tr = self.transcribe_audio_file(path, key)
            if not tr:
                result["error"] = "Transcription: échec"
                return result

            # Analyse GPT (optionnelle)
            self._update_step(key, "gpt_analysis", "Analyse GPT…", 80)
            try:
                try:
                    from backend.gpt_analysis_service import analyze_transcription_with_gpt
                except Exception:
                    from gpt_analysis_service import analyze_transcription_with_gpt
                gpt_analysis = analyze_transcription_with_gpt(tr["text"], cfg["name"])
            except Exception as e:
                logger.warning(f"Analyse GPT indispo: {e}")
                summ = tr["text"][:400] + ("…" if len(tr["text"]) > 400 else "")
                gpt_analysis = {
                    "gpt_analysis": f"📻/📺 Extrait : {summ}",
                    "summary": f"📻/📺 Extrait : {summ}",
                    "analysis_method": "fallback_local",
                    "status": "fallback",
                    "analysis_metadata": {"fallback": True},
                }

            self._update_step(key, "completed", "Sauvegarde…", 95)

            record = {
                "id": f"{key}_{int(time.time())}",
                "stream_key": key,
                "stream_name": cfg["name"],
                "section": cfg["section"],
                "description": cfg["description"],
                "stream_url": cfg["url"],
                "type": cfg.get("type", "radio"),
                "transcription_text": tr["text"],
                "language": tr.get("language", "fr"),
                "duration_seconds": tr.get("duration", duration_seconds),
                "segments": tr.get("segments", []),
                "transcription_method": tr.get("method", "openai_whisper_api"),
                "gpt_analysis": gpt_analysis.get("gpt_analysis", gpt_analysis.get("summary", "")),
                "ai_summary": gpt_analysis.get("gpt_analysis", gpt_analysis.get("summary", "")),
                "analysis_method": gpt_analysis.get("analysis_method", "gpt-4o-mini"),
                "analysis_status": gpt_analysis.get("status", "success"),
                "ai_analysis_metadata": gpt_analysis.get("analysis_metadata", {}),
                "captured_at": datetime.now(TZ).isoformat(),
                "date": datetime.now(TZ).strftime("%Y-%m-%d"),
                "priority": cfg["priority"],
                "start_time_local": f"{cfg['schedule']['hour']:02d}:{cfg['schedule']['minute']:02d}",
                "timezone": TIMEZONE_NAME,
            }

            self.transcriptions_collection.insert_one(record.copy())

            result["success"] = True
            result["transcription"] = record
            self._update_step(key, "completed", "✅ Terminé", 100)

        except Exception as e:
            result["error"] = str(e)
            self._update_step(key, "error", f"Erreur: {e}", 0)
            logger.error(f"Erreur pipeline {cfg['section']}: {e}")
        finally:
            try:
                if path and os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass

        return result

    # =========================
    # Orchestration horaire
    # =========================
    def list_schedules(self) -> List[Dict[str, Any]]:
        out = []
        for k, cfg in self.streams.items():
            sch = cfg["schedule"]
            out.append({
                "key": k,
                "name": cfg["name"],
                "section": cfg["section"],
                "days": self._expand_days(sch.get("days")),
                "hour": sch["hour"],
                "minute": sch["minute"],
                "duration_minutes": cfg["duration_minutes"],
            })
        return out

    def due_stream_keys(self, now_utc: Optional[datetime] = None, window_min: int = 2) -> List[str]:
        pair = self._now_pair(now_utc)
        now_local = pair["local"]
        due = []
        for k, cfg in self.streams.items():
            if self._is_due_now(cfg, now_local, window_min=window_min):
                key_minute = now_local.strftime("%Y-%m-%d %H:%M")
                last = self._last_run_minute.get(k)
                if last == key_minute:
                    # déjà lancé cette minute → on ignore
                    continue
                due.append(k)
        return due

    def capture_due_streams(self, now_utc: Optional[datetime] = None, window_min: int = 2) -> Dict[str, Any]:
        pair = self._now_pair(now_utc)
        now_local = pair["local"]
        due = self.due_stream_keys(now_utc=pair["utc"], window_min=window_min)

        results = {
            "timezone": TIMEZONE_NAME,
            "now_local": now_local.isoformat(),
            "now_utc": pair["utc"].isoformat(),
            "due": due,
            "ran": [],
            "errors": [],
        }

        threads: List[threading.Thread] = []
        thread_res: Dict[str, Dict[str, Any]] = {}

        def _run(k: str):
            thread_res[k] = self.capture_and_transcribe_stream(k)

        for k in due:
            self._last_run_minute[k] = now_local.strftime("%Y-%m-%d %H:%M")
            th = threading.Thread(target=_run, args=(k,))
            th.start()
            threads.append(th)

        for th in threads:
            th.join()

        for k in due:
            r = thread_res.get(k, {})
            if r.get("success"):
                results["ran"].append(k)
            else:
                results["errors"].append({k: r.get("error")})

        return results

    # =========================
    # Lecture / API simples
    # =========================
    def get_todays_transcriptions(self) -> List[Dict[str, Any]]:
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        return list(
            self.transcriptions_collection.find({"date": today}, {"_id": 0}).sort("captured_at", -1)
        )

    def get_transcriptions_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        return list(
            self.transcriptions_collection.find({"date": date_str}, {"_id": 0}).sort("captured_at", -1)
        )


# Instance globale
radio_service = RadioTranscriptionService()

def run_morning_radio_capture():
    # Gardé pour compat, mais non utilisé avec les nouveaux créneaux
    logger.info("⏰ Capture 'matinale' (compat)")
    return radio_service.capture_due_streams()
