# backend/radio_service.py
"""
Service de capture & transcription des flux (radio/TV) Guadeloupe.
- TZ locale America/Guadeloupe
- Capture via FFmpeg (URL directes ou résolues via streamlink)
- Transcription Whisper API (OpenAI) + fallback résumé local
- Dédup minute distribuée (Mongo) pour éviter chevauchements
- GridFS pour stockage audio + transcriptions
- UI status en temps réel + progress
"""

import os
import re
import time
import logging
import hashlib
import subprocess
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pymongo import MongoClient, errors as mongo_errors
from pymongo.errors import DuplicateKeyError
import gridfs
import certifi

logger = logging.getLogger("radio_service")
logger.setLevel(logging.INFO)

# =========================
# Config & TZ locale
# =========================
TIMEZONE_NAME = (os.environ.get("TIMEZONE") or "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TZ = ZoneInfo("UTC")
    TIMEZONE_NAME = "UTC"
    logger.warning("⚠️ TIMEZONE invalide, fallback UTC")

MONGO_URL = (os.environ.get("MONGO_URL") or "mongodb://localhost:27017").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MAX_CONCURRENCY = int(os.environ.get("RADIO_CONCURRENCY", "3"))

# =========================
# Service Principal
# =========================
class RadioTranscriptionService:
    REQUIRED_STREAM_FIELDS = {"name", "section", "url", "schedule", "duration_minutes"}

    def __init__(self):
        # Connexion Mongo
        try:
            if MONGO_URL.startswith("mongodb+srv"):
                self.client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=30000)
            else:
                self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=30000)
            self.client.admin.command("ping")
            try:
                self.db = self.client.get_default_database()
            except mongo_errors.ConfigurationError:
                self.db = self.client["veille_media"]
            logger.info("🔗 Mongo connecté (%s)", self.db.name)
        except Exception as e:
            logger.error("💥 Mongo indisponible: %s", e)
            self.client = self.db = None

        # Collections
        if self.db is not None:
            self.transcriptions_collection = self.db["radio_transcriptions"]
            self.locks_collection = self.db["radio_minute_locks"]
            try:
                self.locks_collection.create_index([("stream_key", 1), ("minute_slot", 1)], unique=True)
                self.locks_collection.create_index("expireAt", expireAfterSeconds=0)
            except Exception as idx_err:
                logger.warning("⚠️ Index creation radio: %s", idx_err)
            self.grid_fs = gridfs.GridFS(self.db, collection="radio_audio")
        else:
            self.transcriptions_collection = self.locks_collection = self.grid_fs = None

        # Définition des flux
        self.streams = {
            "rci_0620": {
                "name": "RCI Journal 6h20",
                "section": "6H20 RCI",
                "description": "RCI — Journal matinal 6h20",
                "type": "radio",
                "url": "https://n10.rcs.revma.com/v4hf7bwspwzuv",
                "duration_minutes": 25,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 6, "minute": 20},
                "priority": 1,
                "enabled": True,
            },
            "rci_0700": {
                "name": "RCI Journal 7h00",
                "section": "7H RCI",
                "description": "RCI — Journal matinal 7h00",
                "type": "radio",
                "url": "https://n10.rcs.revma.com/v4hf7bwspwzuv",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 7, "minute": 0},
                "priority": 2,
                "enabled": True,
            },
            "rci_1300": {
                "name": "RCI Journal 12h00",
                "section": "13H RCI",
                "description": "RCI — Journal de midi",
                "type": "radio",
                "url": "https://n10.rcs.revma.com/v4hf7bwspwzuv",
                "duration_minutes": 30,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 12, "minute": 0},
                "priority": 3,
                "enabled": True,
            },
            "rci_1900": {
                "name": "RCI Journal 19h00",
                "section": "19H RCI",
                "description": "RCI — Journal du soir",
                "type": "radio",
                "url": "https://n10.rcs.revma.com/v4hf7bwspwzuv",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 19, "minute": 0},
                "priority": 4,
                "enabled": True,
            },
            # GP TV désactivés — supprimés (pas de flux audio capturable)
            # rci_0730 (Matin Libre) retiré — émission politique, pas journal d'info
            "rci_1800": {
                "name": "RCI Journal 18h00",
                "section": "18H RCI",
                "description": "RCI — Journal du soir 18h",
                "type": "radio",
                "url": "https://n10.rcs.revma.com/v4hf7bwspwzuv",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 18, "minute": 0},
                "priority": 7,
                "enabled": True,
            },
            "gp_radio_0615": {
                "name": "Guadeloupe 1ère Radio 6h15",
                "section": "6H15 Guadeloupe 1ère",
                "description": "Guadeloupe 1ère — Journal matinal 6h15",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 6, "minute": 15},
                "priority": 8,
                "enabled": True,
            },
            "gp_radio_1200": {
                "name": "Guadeloupe 1ère Radio 12h00",
                "section": "12H Guadeloupe 1ère",
                "description": "Guadeloupe 1ère — Journal de midi",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 12, "minute": 0},
                "priority": 9,
                "enabled": True,
            },
            "gp_radio_1800": {
                "name": "Guadeloupe 1ère Radio 18h00",
                "section": "18H Guadeloupe 1ère",
                "description": "Guadeloupe 1ère — Journal du soir",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 20,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 18, "minute": 0},
                "priority": 10,
                "enabled": True,
            },
            "gp_radio_0700": {
                "name": "Guadeloupe 1ère Radio 7h00",
                "section": "7H Guadeloupe 1ère",
                "description": "Guadeloupe 1ère — Journal matinal 7h",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 34,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 7, "minute": 0},
                "priority": 11,
                "enabled": True,
            },
            "gp_radio_0600": {
                "name": "Guadeloupe 1ère Radio 6h00",
                "section": "6H Guadeloupe 1ère",
                "description": "Guadeloupe 1ère — Journal matinal 6h",
                "type": "radio",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 15,
                "schedule": {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "hour": 6, "minute": 0},
                "priority": 12,
                "enabled": True,
            }
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
        self._status_lock = threading.Lock()

        # Garde-fou local (clé = "YYYY-MM-DD HH:MM")
        self._last_run_minute: Dict[str, str] = {}

        # Validation de config streams
        self._validate_streams()

        # Nettoyage initial des statuts
        self.cleanup_stale_status()

    def _validate_streams(self) -> None:
        """Validation de la configuration des streams"""
        seen = set()
        for k, cfg in self.streams.items():
            if k in seen:
                raise ValueError(f"Duplicate stream key: {k}")
            seen.add(k)
            missing = self.REQUIRED_STREAM_FIELDS - set(cfg.keys())
            if missing:
                raise ValueError(f"Stream {k} missing fields: {missing}")
            sch = cfg.get("schedule") or {}
            h = int(sch.get("hour", 0))
            m = int(sch.get("minute", 0))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError(f"Stream {k} invalid schedule time: {h:02d}:{m:02d}")

    @staticmethod
    def _dow_tag(dt_local: datetime) -> str:
        """Convertir datetime en tag jour de semaine"""
        return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt_local.weekday()]

    @staticmethod
    def _expand_days(days: Any) -> List[str]:
        """Expansion des jours de planification"""
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
        """Paire UTC/Local pour les calculs"""
        if now_utc is None:
            now_utc = datetime.now(ZoneInfo("UTC"))
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
        return {"utc": now_utc, "local": now_utc.astimezone(TZ)}

    def _is_due_now(self, cfg: Dict[str, Any], now_local: datetime, window_min: int = 2) -> bool:
        """Vérifier si un flux est dû maintenant"""
        if not cfg.get("enabled", True):
            return False
        sch = cfg.get("schedule") or {}
        days = set(self._expand_days(sch.get("days")))
        if self._dow_tag(now_local) not in days:
            return False
        hour = int(sch.get("hour", 0))
        minute = int(sch.get("minute", 0))
        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = abs((now_local - target).total_seconds()) / 60.0
        return delta < max(1, window_min)

    def resolve_input_url(self, url: str) -> str:
        """Résolution d'URL via streamlink si nécessaire"""
        try:
            lowered = (url or "").lower()
            if lowered.endswith((".mp3", ".m3u8")):
                return url

            # API Streamlink
            try:
                from streamlink import Streamlink
                session = Streamlink()
                streams = session.streams(url)
                if streams:
                    stream = streams.get("best") or next(iter(streams.values()))
                    return stream.url
            except Exception as e:
                logger.warning("Streamlink failed for %s: %s", url, e)

            # Fallback: retourner l'URL originale
            return url
        except Exception as e:
            logger.warning("URL resolution failed for %s: %s", url, e)
            return url

    def _update_status(self, key: str, **kwargs) -> None:
        """Mise à jour thread-safe du statut"""
        if key not in self.status:
            return
        with self._status_lock:
            for k, v in kwargs.items():
                self.status[key][k] = v
            self.status[key]["last_update"] = datetime.now(TZ).isoformat()

    def cleanup_stale_status(self) -> None:
        """Nettoyer les statuts obsolètes"""
        cutoff = datetime.now(TZ) - timedelta(hours=2)
        with self._status_lock:
            for key in self.status:
                last = self.status[key].get("started_at")
                if last and datetime.fromisoformat(last.replace("Z", "+00:00")) < cutoff:
                    self.status[key].update({
                        "in_progress": False,
                        "current_step": "idle",
                        "step_details": "Timeout - nettoyé",
                        "progress_percentage": 0,
                    })

    def capture_and_transcribe_stream(self, key: str, duration_override_secs: Optional[int] = None) -> Dict[str, Any]:
        """Capture et transcription d'un flux"""
        if key not in self.streams:
            return {"success": False, "error": f"Stream key unknown: {key}"}

        cfg = self.streams[key]
        duration_secs = duration_override_secs or (cfg["duration_minutes"] * 60)
        resolved_url = self.resolve_input_url(cfg["url"])

        # Mise à jour statut
        self._update_status(key, 
            in_progress=True, 
            current_step="capture",
            step_details=f"Capture {duration_secs}s",
            started_at=datetime.now(TZ).isoformat(),
            progress_percentage=10
        )

        try:
            # Capture audio en MP3 (plus compact que WAV, respecte la limite Whisper 25MB)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            cmd = [
                "ffmpeg", "-y", "-i", resolved_url,
                "-t", str(duration_secs),
                "-ar", "16000", "-ac", "1",
                "-codec:a", "libmp3lame", "-b:a", "64k",
                tmp_path
            ]

            self._update_status(key, progress_percentage=30)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_secs + 60)

            if result.returncode != 0:
                os.unlink(tmp_path)
                self._update_status(key, in_progress=False, current_step="error")
                return {"success": False, "error": f"FFmpeg failed: {result.stderr[-500:]}"}

            # Vérifier la taille avant envoi à Whisper (limite 25MB)
            file_size = os.path.getsize(tmp_path)
            logger.info(f"🎙️ {key}: capture {file_size / 1024 / 1024:.1f}MB ({duration_secs}s)")
            if file_size > 25 * 1024 * 1024:
                logger.warning(f"⚠️ {key}: fichier trop gros ({file_size / 1024 / 1024:.1f}MB), re-compression...")
                # Re-compresser en bitrate plus bas
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp2:
                    tmp_path2 = tmp2.name
                cmd2 = ["ffmpeg", "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1",
                        "-codec:a", "libmp3lame", "-b:a", "32k", tmp_path2]
                subprocess.run(cmd2, capture_output=True, timeout=120)
                os.unlink(tmp_path)
                tmp_path = tmp_path2

            self._update_status(key, current_step="transcription", progress_percentage=60)

            # Transcription
            transcription_text = self._transcribe_audio(tmp_path)

            self._update_status(key, current_step="saving", progress_percentage=80)

            # Sauvegarde
            doc = self._save_transcription(key, cfg, tmp_path, transcription_text)

            # Nettoyage
            os.unlink(tmp_path)
            
            self._update_status(key, 
                in_progress=False, 
                current_step="completed",
                progress_percentage=100
            )
            
            return {"success": True, "transcription": doc}

        except Exception as e:
            if 'tmp_path' in locals():
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            self._update_status(key, 
                in_progress=False, 
                current_step="error",
                step_details=str(e)
            )
            return {"success": False, "error": str(e)}

    def _transcribe_audio(self, audio_path: str) -> str:
        """Transcription audio via OpenAI Whisper"""
        if not OPENAI_API_KEY:
            return "[Transcription indisponible - clé OpenAI manquante]"
        
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="fr"
                )
            return response.text
        except Exception as e:
            logger.warning("Transcription OpenAI failed: %s", e)
            return f"[Erreur transcription: {e}]"

    def _save_transcription(self, key: str, cfg: Dict[str, Any], audio_path: str, text: str) -> Dict[str, Any]:
        """Sauvegarde transcription et audio"""
        now_utc = datetime.now(ZoneInfo("UTC"))
        now_local = now_utc.astimezone(TZ)
        
        # Sauvegarde audio dans GridFS
        audio_file_id = None
        if self.grid_fs is not None and os.path.exists(audio_path):
            try:
                with open(audio_path, "rb") as f:
                    audio_file_id = self.grid_fs.put(
                        f,
                        filename=f"{key}_{now_local.strftime('%Y%m%d_%H%M')}.wav",
                        content_type="audio/wav",
                        metadata={
                            "stream_key": key,
                            "captured_at": now_utc,
                            "section": cfg.get("section", ""),
                            "type": cfg.get("type", "radio")
                        }
                    )
            except Exception as e:
                logger.warning("GridFS save failed: %s", e)

        # Document transcription
        # Extraire le nom de la radio (ex: "RCI Journal 7h00" → "RCI")
        radio_name = cfg["name"].split()[0] if cfg["name"] else key.split("_")[0].upper()
        doc = {
            "stream_key": key,
            "name": cfg["name"],
            "radio": radio_name,
            "stream_name": cfg["name"],
            "section": cfg["section"],
            "type": cfg.get("type", "radio"),
            "url": cfg["url"],
            "text": text,
            "transcription": text,
            "captured_at": now_utc.isoformat(),
            "captured_at_local": now_local.isoformat(),
            "date": now_local.strftime("%Y-%m-%d"),
            "time": now_local.strftime("%H:%M"),
            "timezone": TIMEZONE_NAME,
            "duration_minutes": cfg["duration_minutes"],
            "audio_file_id": str(audio_file_id) if audio_file_id else None,
            "text_length": len(text),
            "status": "completed"
        }

        # Sauvegarde en collection
        if self.transcriptions_collection is not None:
            try:
                self.transcriptions_collection.insert_one(doc.copy())
            except Exception as e:
                logger.warning("Transcription save failed: %s", e)

        # 📢 Notification Telegram du résumé radio
        try:
            from backend.services.telegram_service import notify_radio_summary
            notify_radio_summary(doc)
        except Exception as tg_err:
            logger.debug(f"Telegram notif radio: {tg_err}")

        return doc

    def _minute_slot_str(self, dt_local: datetime) -> str:
        """Slot minute pour verrouillage"""
        return dt_local.strftime("%Y-%m-%d %H:%M")

    def _acquire_minute_lock(self, stream_key: str, minute_slot: str) -> bool:
        """Acquisition de verrou minute distribué"""
        if self.locks_collection is None:
            return True

        expire_at = datetime.now(TZ) + timedelta(minutes=15)
        try:
            self.locks_collection.insert_one({
                "stream_key": stream_key,
                "minute_slot": minute_slot,
                "createdAt": datetime.now(TZ),
                "expireAt": expire_at
            })
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            logger.warning("Lock insert error: %s", e)
            return False

    def _release_minute_lock(self, stream_key: str, minute_slot: str) -> None:
        """Libération de verrou minute"""
        if self.locks_collection is None:
            return
        try:
            self.locks_collection.delete_one({"stream_key": stream_key, "minute_slot": minute_slot})
        except Exception:
            pass

    def list_schedules(self) -> List[Dict[str, Any]]:
        """Liste des planifications configurées"""
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
                "enabled": cfg.get("enabled", True),
                "type": cfg.get("type", "radio"),
            })
        return out

    def due_stream_keys(self, now_utc: Optional[datetime] = None, window_min: int = 2) -> List[str]:
        """Liste des clés de flux dus maintenant"""
        pair = self._now_pair(now_utc)
        now_local = pair["local"]
        due = []
        for k, cfg in self.streams.items():
            if self._is_due_now(cfg, now_local, window_min=window_min):
                key_minute = now_local.strftime("%Y-%m-%d %H:%M")
                last = self._last_run_minute.get(k)
                if last == key_minute:
                    continue
                due.append(k)
        return due

    def capture_due_streams(self, now_utc: Optional[datetime] = None, window_min: int = 2) -> Dict[str, Any]:
        """Capture des flux dus avec gestion concurrence"""
        pair = self._now_pair(now_utc)
        now_local = pair["local"]
        due_all = self.due_stream_keys(now_utc=pair["utc"], window_min=window_min)

        results = {
            "timezone": TIMEZONE_NAME,
            "now_local": now_local.isoformat(),
            "now_utc": pair["utc"].isoformat(),
            "due": [],
            "skipped_locked": [],
            "ran": [],
            "errors": [],
        }

        # Acquisition des locks distribués
        to_run: List[str] = []
        minute_slot = self._minute_slot_str(now_local)
        for k in due_all:
            if self._acquire_minute_lock(k, minute_slot):
                self._last_run_minute[k] = minute_slot
                to_run.append(k)
            else:
                results["skipped_locked"].append(k)

        results["due"] = to_run
        if not to_run:
            return results

        # Exécutions simultanées plafonnées
        futures = {}

        def _runner(k: str) -> Dict[str, Any]:
            try:
                # Jitter déterministe
                time.sleep((int(hashlib.md5(k.encode()).hexdigest(), 16) % 1200) / 1000.0)
                return self.capture_and_transcribe_stream(k)
            finally:
                self._release_minute_lock(k, minute_slot)

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY, thread_name_prefix="radio-cap") as ex:
            for k in to_run:
                futures[ex.submit(_runner, k)] = k

            for fut in as_completed(futures):
                k = futures[fut]
                try:
                    r = fut.result()
                    if r.get("success"):
                        results["ran"].append(k)
                    else:
                        results["errors"].append({k: r.get("error")})
                except Exception as e:
                    results["errors"].append({k: str(e)})

        return results

    # NOUVELLE MÉTHODE ASYNC POUR LE SCHEDULER
    async def capture_due_streams_async(self, now_utc: Optional[datetime] = None, window_min: int = 2) -> Dict[str, Any]:
        """
        Version asynchrone de capture_due_streams pour compatibilité avec le scheduler async.
        Délègue à la méthode synchrone existante via un executor.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        # Exécuter la méthode synchrone dans un thread séparé
        return await loop.run_in_executor(
            None, 
            self.capture_due_streams, 
            now_utc, 
            window_min
        )

    def get_todays_transcriptions(self) -> List[Dict[str, Any]]:
        """Transcriptions du jour"""
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        try:
            cur = self.transcriptions_collection.find({"date": today}, {"_id": 0}).sort("captured_at", -1)
            return list(cur)
        except Exception as e:
            logger.warning("Mongo read todays_transcriptions: %s", e)
            return []

    def get_transcriptions_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Transcriptions par date"""
        try:
            cur = self.transcriptions_collection.find({"date": date_str}, {"_id": 0}).sort("captured_at", -1)
            return list(cur)
        except Exception as e:
            logger.warning("Mongo read transcriptions_by_date: %s", e)
            return []

    def is_ready(self) -> bool:
        """Vérification de l'état du service"""
        return self.db is not None and self.transcriptions_collection is not None


# Instance globale — proxy paresseux : la connexion Mongo (et son timeout) n'a lieu
# qu'au premier accès réel, pas à l'import. Rend le module importable sans Mongo (tests/CI).
class _LazyRadioService:
    __slots__ = ("_inst",)

    def __init__(self):
        self._inst = None

    def _get(self):
        if self._inst is None:
            self._inst = RadioTranscriptionService()
        return self._inst

    def __getattr__(self, name):
        return getattr(self._get(), name)


radio_service = _LazyRadioService()

def run_morning_radio_capture():
    """Compatibilité legacy"""
    logger.info("⏰ Capture 'matinale' (compat)")
    return radio_service.capture_due_streams()
