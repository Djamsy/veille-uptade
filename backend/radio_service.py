# backend/radio_service.py
"""
Service de capture & transcription des flux radio guadeloupéens.
- Capture “réelle” (FFmpeg), transcription OpenAI Whisper API
- Analyse GPT (résumé journalistique)
- Capture segmentée pour les durées longues
- Alias de sections (rci -> rci_7h, etc.)
"""

import os
import subprocess
import tempfile
from datetime import datetime, timedelta
import logging
import shutil
from pymongo import MongoClient
from typing import Dict, Any, Optional, List
import threading
import time

logger = logging.getLogger(__name__)

# Permet de surcharger le chemin de ffmpeg (utile sur mac/brew)
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

# User-Agent et Referer par défaut pour certains flux
DEFAULT_UA = os.environ.get("FFMPEG_UA", "Mozilla/5.0 (compatible; VeilleRadio/1.0; +https://example.local)")
LA1ERE_REFERER = "https://la1ere.franceinfo.fr/"


def _resolve_ffmpeg_bin():
    """
    Vérifie que FFMPEG_BIN pointe vers un binaire existant. Si non, tente de trouver 'ffmpeg' via PATH.
    Log une info si on bascule, ou une erreur explicite si introuvable.
    """
    global FFMPEG_BIN
    try:
        if not os.path.exists(FFMPEG_BIN):
            alt = shutil.which("ffmpeg")
            if alt:
                FFMPEG_BIN = alt
                logger.info(f"⚙️ FFmpeg détecté via PATH: {FFMPEG_BIN}")
            else:
                logger.error(
                    "❌ FFmpeg introuvable. Définissez FFMPEG_BIN ou installez ffmpeg (brew install ffmpeg)."
                )
    except Exception as e:
        logger.warning(f"⚠️ Vérification FFMPEG_BIN: {e}")


class RadioTranscriptionService:
    def __init__(self):
        # MongoDB
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.transcriptions_collection = self.db.radio_transcriptions

        # Vérifier / auto-résoudre FFmpeg
        _resolve_ffmpeg_bin()

        # Flux connus
        self.radio_streams = {
            "rci_7h": {
                "name": "7H RCI",
                "description": "RCI Guadeloupe - Journal matinal",
                "url": "http://n01a-eu.rcs.revma.com/v4hf7bwspwzuv?rj-ttl=5&rj-tok=AAABmFgYf1YAGI3rfz2-KTLPnA",
                "duration_minutes": 20,
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H RCI",
                "priority": 1,
            },
            "guadeloupe_premiere_7h": {
                "name": "7H Guadeloupe Première",
                "description": "Guadeloupe Première - Actualités matinales",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 30,
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H Guadeloupe Première",
                "priority": 2,
            },
        }

        # Statuts (UI)
        self.transcription_status: Dict[str, Dict[str, Any]] = {
            key: {
                "in_progress": False,
                "current_step": "idle",  # idle | audio_capture | transcription | gpt_analysis | completed | error
                "step_details": "",
                "started_at": None,
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None,
            }
            for key in self.radio_streams.keys()
        }

        self.cleanup_stale_status()

    # ---------- Résolution d'URL jouable (page -> m3u8/mp3) ----------
    def resolve_input_url(self, url: str) -> str:
        """Résout une URL de page (ex: la1ere.franceinfo...) en URL de flux lisible par ffmpeg.
        Essaie d'abord via l'API Python de streamlink, puis via le binaire `streamlink --stream-url`.
        En cas d'échec, renvoie l'URL d'origine.
        """
        try:
            # Si c'est déjà un flux direct, on renvoie tel quel
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
                    # Certaines versions exposent .to_url(), d'autres .url
                    if hasattr(stream, "to_url"):
                        try:
                            real_url = stream.to_url()  # type: ignore[attr-defined]
                        except Exception:
                            real_url = None
                    if not real_url:
                        real_url = getattr(stream, "url", None)
                    if isinstance(real_url, str) and real_url:
                        # Nettoyage des préfixes streamlink (ex: hlsvariant://)
                        for prefix in ("hlsvariant://", "hls://"):
                            if real_url.startswith(prefix):
                                real_url = real_url[len(prefix):]
                        logger.info(f"🎯 URL résolue via streamlink (API): {real_url}")
                        return real_url
            except Exception as e:
                logger.debug(f"Streamlink API indisponible/échec: {e}")

            # Fallback: binaire streamlink --stream-url
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
                    logger.info(f"🎯 URL résolue via streamlink (CLI): {out}")
                    return out
                else:
                    logger.debug(f"streamlink CLI a échoué (rc={proc.returncode}): {proc.stderr}")
            except Exception as e:
                logger.debug(f"streamlink CLI indisponible/échec: {e}")
        except Exception as e:
            logger.warning(f"⚠️ resolve_input_url: {e}")
        return url

    # ---------- Utilitaires statut ----------

    def update_transcription_step(
        self, stream_key: str, step: str, details: str = "", progress: int = 0
    ):
        if stream_key not in self.transcription_status:
            return
        st = self.transcription_status[stream_key]
        st["current_step"] = step
        st["step_details"] = details
        st["progress_percentage"] = progress
        st["last_update"] = datetime.now().isoformat()

        if step == "audio_capture" and not st["in_progress"]:
            st["in_progress"] = True
            st["started_at"] = datetime.now().isoformat()
            st["cache_expires_at"] = (datetime.now() + timedelta(hours=24)).isoformat()

        if step in ("completed", "error"):
            st["in_progress"] = False
            st["started_at"] = None
            st["estimated_completion"] = None
            if step == "completed":
                st["progress_percentage"] = 100

        stream_name = self.radio_streams.get(stream_key, {}).get("name", stream_key)
        logger.info(f"🔄 {stream_name}: {step} - {details} ({progress}%)")

    def reset_all_transcription_status(self):
        for key in self.transcription_status:
            self.transcription_status[key] = {
                "in_progress": False,
                "current_step": "idle",
                "step_details": "",
                "started_at": None,
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None,
            }

    def cleanup_stale_status(self):
        now = datetime.now()
        for key, st in self.transcription_status.items():
            if st["in_progress"] and st["started_at"]:
                try:
                    started = datetime.fromisoformat(st["started_at"])
                    if now - started > timedelta(hours=2):
                        logger.warning(
                            f"🧹 Statut expiré nettoyé pour {self.radio_streams[key]['name']}"
                        )
                        self.update_transcription_step(
                            key, "error", "Statut expiré - nettoyage automatique", 0
                        )
                except Exception as e:
                    logger.error(f"Erreur cleanup statut {key}: {e}")
                    self.update_transcription_step(key, "idle", "Réinitialisé", 0)

    # ---------- Alias / compat front ----------

    def resolve_stream_key(self, section: str) -> str:
        s = (section or "").lower().strip()
        aliases = {
            "rci": "rci_7h",
            "7h rci": "rci_7h",
            "rci_7h": "rci_7h",

            "premiere": "guadeloupe_premiere_7h",
            "1ere": "guadeloupe_premiere_7h",
            "la1ere": "guadeloupe_premiere_7h",
            "la 1ere": "guadeloupe_premiere_7h",
            "la première": "guadeloupe_premiere_7h",
            "guadeloupe premiere": "guadeloupe_premiere_7h",
            "guadeloupe première": "guadeloupe_premiere_7h",
            "7h guadeloupe première": "guadeloupe_premiere_7h",
            "7h guadeloupe 1ere": "guadeloupe_premiere_7h",
            "7h la 1ere": "guadeloupe_premiere_7h",
            "7h la première": "guadeloupe_premiere_7h",
            "guadeloupe_premiere_7h": "guadeloupe_premiere_7h",
            # Added aliases:
            "guadeloupe": "guadeloupe_premiere_7h",
            "guadeloupe1ere": "guadeloupe_premiere_7h",
            "guadeloupe_1ere": "guadeloupe_premiere_7h",
            "franceinfo guadeloupe": "guadeloupe_premiere_7h",
            "france info guadeloupe": "guadeloupe_premiere_7h",
        }
        return aliases.get(s, s)

    def capture_stream(self, section: str, duration_seconds: int) -> Optional[str]:
        """
        Méthode attendue par certaines routes (alias).
        Capture brute de `section` pendant `duration_seconds` et renvoie le chemin du .mp3 temp.
        """
        key = self.resolve_stream_key(section)
        if key not in self.radio_streams:
            raise ValueError(f"Section inconnue: {section} (résolue: {key})")
        return self.capture_radio_stream(key, duration_seconds)

    # ---------- Capture (simple / segmentée) ----------

    def capture_radio_stream(self, stream_key: str, duration_seconds: int) -> Optional[str]:
        """Capture simple (durées courtes)."""
        cfg = self.radio_streams[stream_key]
        self.update_transcription_step(
            stream_key, "audio_capture", f"Capture audio ({duration_seconds}s)", 10
        )
        logger.info(f"🎵 Capture {cfg['name']} pendant {duration_seconds}s…")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            temp_path = tmp.name

        input_url = self.resolve_input_url(cfg["url"])
        headers_args: List[str] = []
        if "la1ere.franceinfo.fr" in (input_url or cfg["url"]):
            headers_args = ["-headers", f"Referer: {LA1ERE_REFERER}\r\n"]

        cmd = [
            FFMPEG_BIN,
            "-hide_banner", "-loglevel", "warning",
            "-user_agent", DEFAULT_UA,
            *headers_args,
            "-i", input_url,
            "-t", str(duration_seconds),
            "-acodec", "mp3",
            "-ar", "16000",
            "-ac", "1",
            "-y", temp_path,
        ]

        try:
            subprocess.run(
                cmd, capture_output=True, timeout=duration_seconds + 30, check=True
            )
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
                size = os.path.getsize(temp_path)
                self.update_transcription_step(
                    stream_key, "transcription", f"Audio capturé ({size/1024:.1f}KB)", 40
                )
                logger.info(f"✅ Audio capturé: {size} bytes")
                return temp_path
            logger.error("❌ Fichier audio vide")
        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout ffmpeg (capture)")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Erreur ffmpeg (capture): {e}")
        except Exception as e:
            logger.error(f"❌ Erreur capture: {e}")

        if os.path.exists(temp_path):
            os.unlink(temp_path)
        self.update_transcription_step(stream_key, "error", "Échec capture", 0)
        return None

    def capture_radio_stream_segmented(
        self, stream_key: str, total_duration_seconds: int, segment_duration: int = 300
    ) -> List[str]:
        """Capture par segments (par défaut 5min/segment) — robuste pour longues durées."""
        cfg = self.radio_streams[stream_key]
        paths: List[str] = []

        num_segments = (total_duration_seconds + segment_duration - 1) // segment_duration
        logger.info(
            f"🎬 Capture segmentée {cfg['name']}: {total_duration_seconds}s en {num_segments}×{segment_duration}s"
        )

        for idx in range(num_segments):
            remain = total_duration_seconds - (idx * segment_duration)
            dur = min(segment_duration, remain)

            progress = int(10 + (idx / max(1, num_segments)) * 30)  # 10 → 40
            self.update_transcription_step(
                stream_key, "audio_capture", f"Segment {idx+1}/{num_segments} ({dur}s)", progress
            )

            with tempfile.NamedTemporaryFile(suffix=f"_seg{idx}.mp3", delete=False) as tmp:
                seg_path = tmp.name

            input_url = self.resolve_input_url(cfg["url"])
            headers_args: List[str] = []
            if "la1ere.franceinfo.fr" in (input_url or cfg["url"]):
                headers_args = ["-headers", f"Referer: {LA1ERE_REFERER}\r\n"]

            cmd = [
                FFMPEG_BIN,
                "-hide_banner", "-loglevel", "warning",
                "-user_agent", DEFAULT_UA,
                *headers_args,
                "-i", input_url,
                "-t", str(dur),
                "-acodec", "mp3",
                "-ar", "16000",
                "-ac", "1",
                "-y", seg_path,
            ]

            try:
                subprocess.run(cmd, capture_output=True, timeout=dur + 60, check=True)
                if os.path.exists(seg_path) and os.path.getsize(seg_path) > 1000:
                    paths.append(seg_path)
                    logger.info(f"✅ Segment {idx+1} OK: {os.path.getsize(seg_path)} bytes")
                else:
                    logger.warning(f"⚠️ Segment {idx+1} vide")
                    if os.path.exists(seg_path):
                        os.unlink(seg_path)
            except Exception as e:
                logger.error(f"❌ Segment {idx+1} erreur: {e}")
                if os.path.exists(seg_path):
                    os.unlink(seg_path)

        if not paths:
            logger.error("❌ Aucun segment valide")
        else:
            logger.info(f"🎬 Segments capturés: {len(paths)}/{num_segments}")
        return paths

    def concatenate_audio_segments(self, segments_paths: List[str], stream_key: str) -> Optional[str]:
        if not segments_paths:
            return None

        self.update_transcription_step(stream_key, "audio_capture", "Assemblage segments…", 45)

        with tempfile.NamedTemporaryFile(suffix="_full.mp3", delete=False) as out:
            out_path = out.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as lst:
            list_path = lst.name
            for p in segments_paths:
                lst.write(f"file '{p}'\n")

        cmd = [
            FFMPEG_BIN,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            "-y",
            out_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=180, check=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                logger.info(f"✅ Concat OK: {os.path.getsize(out_path)} bytes")
                return out_path
            logger.error("❌ Concat vide")
            return None
        finally:
            if os.path.exists(list_path):
                os.unlink(list_path)

    # ---------- Transcription & fusion ----------

    def transcribe_audio_file(
        self, audio_path: str, stream_key: str = "unknown"
    ) -> Optional[Dict[str, Any]]:
        """Transcription via OpenAI Whisper API (whisper-1)."""
        try:
            if stream_key != "unknown":
                self.update_transcription_step(
                    stream_key, "transcription", "Transcription OpenAI Whisper…", 60
                )
            logger.info(f"🎤 Transcription OpenAI: {os.path.basename(audio_path)}")

            try:
                # Import paresseux pour éviter erreurs d'import au boot
                from backend.gpt_analysis_service import gpt_analyzer
            except Exception:
                from gpt_analysis_service import gpt_analyzer  # fallback si path diff.

            if not getattr(gpt_analyzer, "client", None):
                raise RuntimeError("Client OpenAI indisponible")

            with open(audio_path, "rb") as f:
                transcript = gpt_analyzer.client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="fr"
                )

            data = {
                "text": (transcript.text or "").strip(),
                "language": "fr",
                "segments": [],  # Whisper API (OpenAI) ne renvoie pas les timecodes par défaut
                "duration": 0,
                "method": "openai_whisper_api",
            }
            if stream_key != "unknown":
                self.update_transcription_step(
                    stream_key, "gpt_analysis", f"Transcription OK ({len(data['text'])} chars)", 70
                )
            logger.info(f"✅ Transcription OK: {len(data['text'])} chars")
            return data
        except Exception as e:
            logger.error(f"❌ Transcription erreur: {e}")
            if stream_key != "unknown":
                self.update_transcription_step(stream_key, "error", f"Transcription: {e}", 0)
            return None

    def transcribe_segments_individually(
        self, segments_paths: List[str], stream_key: str
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        total = len(segments_paths)
        for i, p in enumerate(segments_paths):
            try:
                self.update_transcription_step(
                    stream_key, "transcription", f"Segment {i+1}/{total}…", int(50 + (i / max(1, total)) * 30)
                )
                t = self.transcribe_audio_file(p, "segment")
                if t:
                    t["segment_number"] = i + 1
                    t["segment_path"] = os.path.basename(p)
                    out.append(t)
            except Exception as e:
                logger.error(f"❌ Transcription segment {i+1}: {e}")
        return out

    def merge_transcriptions(self, transcriptions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not transcriptions:
            return None

        full_text = " ".join(t.get("text", "") for t in transcriptions)
        # (On ne dispose pas des timecodes via API → segments=[])

        merged = {
            "text": full_text,
            "language": "fr",
            "segments": [],
            "duration": sum(t.get("duration", 0) for t in transcriptions),
            "method": "segmented_openai_whisper_api",
            "segments_count": len(transcriptions),
            "segments_info": [{"segment": i + 1, "chars": len(t.get("text", ""))} for i, t in enumerate(transcriptions)],
        }
        logger.info(f"✅ Fusion transcriptions: {len(full_text)} chars (x{len(transcriptions)})")
        return merged

    # ---------- Pipeline complet ----------

    def capture_and_transcribe_stream(
        self,
        stream_key: str,
        use_segmented: Optional[bool] = None,
        duration_override_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        cfg = self.radio_streams[stream_key]
        duration_seconds = duration_override_secs or (cfg["duration_minutes"] * 60)

        # Telegram (optionnel)
        try:
            from backend.telegram_alerts_service import telegram_alerts
        except Exception:
            telegram_alerts = None

        if telegram_alerts and getattr(telegram_alerts, "bot", None):
            try:
                telegram_alerts.send_alert_sync(
                    f"📻 *DÉBUT CAPTURE RADIO*\n\n🎙️ {cfg['name']}\n⏱️ {duration_seconds//60} minutes"
                )
            except Exception:
                pass

        if use_segmented is None:
            use_segmented = duration_seconds > 600  # > 10 min → segmenter

        result: Dict[str, Any] = {
            "success": False,
            "stream_key": stream_key,
            "stream_name": cfg["name"],
            "section": cfg["section"],
            "timestamp": datetime.now().isoformat(),
            "error": None,
            "transcription": None,
            "method": "segmented" if use_segmented else "single",
        }

        segments_paths: List[str] = []
        try:
            self.update_transcription_step(stream_key, "audio_capture", "Initialisation…", 5)

            if use_segmented:
                segments_paths = self.capture_radio_stream_segmented(stream_key, duration_seconds)
                if not segments_paths:
                    result["error"] = "Capture segmentée: échec"
                    return result

                if len(segments_paths) > 3:
                    seg_tr = self.transcribe_segments_individually(segments_paths, stream_key)
                    if not seg_tr:
                        result["error"] = "Transcription segments: échec"
                        return result
                    transcription = self.merge_transcriptions(seg_tr)
                else:
                    concat_path = self.concatenate_audio_segments(segments_paths, stream_key)
                    if not concat_path:
                        result["error"] = "Assemblage segments: échec"
                        return result
                    try:
                        transcription = self.transcribe_audio_file(concat_path, stream_key)
                    finally:
                        if concat_path and os.path.exists(concat_path):
                            os.unlink(concat_path)

                # Nettoyage segments
                for p in segments_paths:
                    if os.path.exists(p):
                        os.unlink(p)

            else:
                audio_path = self.capture_radio_stream(stream_key, duration_seconds)
                if not audio_path:
                    result["error"] = "Capture audio: échec"
                    return result
                try:
                    transcription = self.transcribe_audio_file(audio_path, stream_key)
                finally:
                    if audio_path and os.path.exists(audio_path):
                        os.unlink(audio_path)

            if not transcription:
                result["error"] = "Transcription: vide/échec"
                return result

            # Analyse GPT
            self.update_transcription_step(stream_key, "gpt_analysis", "Analyse GPT…", 80)
            logger.info("🧠 Analyse GPT de la transcription…")

            gpt_analysis = None
            try:
                try:
                    from backend.gpt_analysis_service import analyze_transcription_with_gpt
                except Exception:
                    from gpt_analysis_service import analyze_transcription_with_gpt  # fallback
                gpt_analysis = analyze_transcription_with_gpt(transcription["text"], cfg["name"])
            except Exception as e:
                logger.warning(f"Analyse GPT indisponible, fallback: {e}")
                # Fallback local minimal
                summ = transcription["text"][:400] + ("…" if len(transcription["text"]) > 400 else "")
                gpt_analysis = {
                    "gpt_analysis": f"📻 Journal radio (extrait) : {summ}",
                    "summary": f"📻 Journal radio (extrait) : {summ}",
                    "analysis_method": "fallback_local",
                    "status": "fallback",
                    "analysis_metadata": {"fallback": True},
                }

            self.update_transcription_step(stream_key, "completed", "Sauvegarde…", 95)

            # Sauvegarde DB
            record = {
                "id": f"{stream_key}_{int(time.time())}",
                "stream_key": stream_key,
                "stream_name": cfg["name"],
                "section": cfg["section"],
                "description": cfg["description"],
                "stream_url": cfg["url"],
                "transcription_text": transcription["text"],
                "language": transcription.get("language", "fr"),
                "duration_seconds": transcription.get("duration", duration_seconds),
                "segments": transcription.get("segments", []),
                "transcription_method": transcription.get("method", "openai_whisper_api"),
                "segments_count": transcription.get("segments_count", 1),
                "segments_info": transcription.get("segments_info", []),
                "gpt_analysis": gpt_analysis.get("gpt_analysis", gpt_analysis.get("summary", "")),
                "ai_summary": gpt_analysis.get("gpt_analysis", gpt_analysis.get("summary", "")),
                "analysis_method": gpt_analysis.get("analysis_method", "gpt-4o-mini"),
                "analysis_status": gpt_analysis.get("status", "success"),
                "ai_analysis_metadata": gpt_analysis.get("analysis_metadata", {}),
                "ai_key_sentences": gpt_analysis.get("key_sentences", []),
                "ai_main_topics": gpt_analysis.get("main_topics", []),
                "ai_keywords": gpt_analysis.get("keywords", []),
                "ai_relevance_score": gpt_analysis.get("relevance_score", 0.8),
                "captured_at": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "audio_size_bytes": sum(os.path.getsize(p) for p in segments_paths if os.path.exists(p))
                if use_segmented
                else 0,
                "priority": cfg["priority"],
                "start_time": f"{cfg['start_hour']:02d}:{cfg['start_minute']:02d}",
                "capture_method": "segmented" if use_segmented else "single",
            }

            self.transcriptions_collection.insert_one(record.copy())

            result["success"] = True
            result["transcription"] = record
            self.update_transcription_step(stream_key, "completed", "✅ Terminé", 100)

            # Telegram fin
            if telegram_alerts and getattr(telegram_alerts, "bot", None):
                try:
                    gl = any(k in (record["transcription_text"] + " " + record["ai_summary"]).lower()
                             for k in ["guy losbar", "losbar"])
                    status_emoji = "🎯" if gl else "✅"
                    telegram_alerts.send_alert_sync(
                        f"📻 *TRANSCRIPTION TERMINÉE* {status_emoji}\n\n"
                        f"🎙️ {cfg['name']}\n"
                        f"📝 {len(record['transcription_text'])} caractères\n"
                        f"🤖 {len(record['ai_summary'])} caractères"
                    )
                except Exception:
                    pass

        except Exception as e:
            result["error"] = str(e)
            self.update_transcription_step(stream_key, "error", f"Erreur: {e}", 0)
            logger.error(f"❌ Erreur pipeline {cfg['section']}: {e}")

        return result

    # ---------- Multi flux / lecture ----------

    def capture_all_streams(self) -> Dict[str, Any]:
        logger.info("🚀 Capture de tous les flux radio…")
        results = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "streams_processed": 0,
            "streams_success": 0,
            "transcriptions": [],
            "errors": [],
        }

        threads: List[threading.Thread] = []
        stream_results: Dict[str, Dict[str, Any]] = {}

        def _run(k: str):
            stream_results[k] = self.capture_and_transcribe_stream(k)

        for k in self.radio_streams.keys():
            th = threading.Thread(target=_run, args=(k,))
            th.start()
            threads.append(th)

        for th in threads:
            th.join()

        for k, r in stream_results.items():
            results["streams_processed"] += 1
            if r.get("success"):
                results["streams_success"] += 1
                results["transcriptions"].append(r["transcription"])
            else:
                results["errors"].append(f"{self.radio_streams[k]['name']}: {r.get('error')}")

        results["success"] = results["streams_success"] > 0
        logger.info(
            f"📊 {results['streams_success']}/{results['streams_processed']} flux OK"
        )
        return results

    def get_transcription_status(self) -> Dict[str, Any]:
        summary = {
            "sections": {},
            "global_status": {"any_in_progress": False, "total_sections": len(self.radio_streams), "active_sections": 0},
        }

        step_desc = {
            "idle": "En attente",
            "audio_capture": "📻 Capture audio",
            "transcription": "🎤 Transcription",
            "gpt_analysis": "🧠 Analyse GPT",
            "completed": "✅ Terminé",
            "error": "❌ Erreur",
        }

        for key, cfg in self.radio_streams.items():
            st = self.transcription_status[key].copy()
            st.update(
                {
                    "section_name": cfg["section"],
                    "description": cfg["description"],
                    "duration_minutes": cfg["duration_minutes"],
                    "start_time": f"{cfg['start_hour']:02d}:{cfg['start_minute']:02d}",
                    "priority": cfg["priority"],
                    "step_description": step_desc.get(st["current_step"], st["current_step"]),
                }
            )
            summary["sections"][key] = st
            if st["in_progress"]:
                summary["global_status"]["any_in_progress"] = True
                summary["global_status"]["active_sections"] += 1

        return summary

    def get_todays_transcriptions_by_section(self) -> Dict[str, List]:
        today = datetime.now().strftime("%Y-%m-%d")
        items = list(
            self.transcriptions_collection.find({"date": today}, {"_id": 0}).sort("captured_at", -1)
        )
        sections: Dict[str, List] = {"7H RCI": [], "7H Guadeloupe Première": [], "Autres": []}
        for t in items:
            sec = t.get("section", "Autres")
            (sections[sec] if sec in sections else sections["Autres"]).append(t)
        return sections

    def get_todays_transcriptions(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
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
    logger.info("⏰ Capture radio matinale (7H)")
    return radio_service.capture_all_streams()


if __name__ == "__main__":
    # Test manuel (attention: capture réelle)
    out = radio_service.capture_and_transcribe_stream("rci_7h", duration_override_secs=300)
    print(out)