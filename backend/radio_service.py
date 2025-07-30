"""
Service de capture et transcription des flux radio guadeloupéens
Capture automatique 7H00-7H20 et 7H00-7H30 avec analyse GPT-4.1-mini
"""
import os
import subprocess
import tempfile
import whisper
from datetime import datetime, timedelta
import asyncio
import logging
from pymongo import MongoClient
from typing import Dict, Any, Optional, List
import threading
import time

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RadioTranscriptionService:
    def __init__(self):
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.transcriptions_collection = self.db.radio_transcriptions
        
        # Configuration des flux radio avec sections pré-nommées
        self.radio_streams = {
            "rci_7h": {
                "name": "7H RCI",
                "description": "RCI Guadeloupe - Journal matinal",
                "url": "http://n01a-eu.rcs.revma.com/v4hf7bwspwzuv?rj-ttl=5&rj-tok=AAABmFgYf1YAGI3rfz2-KTLPnA",
                "duration_minutes": 20,  # 7H00-7H20
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H RCI",
                "priority": 1
            },
            "guadeloupe_premiere_7h": {
                "name": "7H Guadeloupe Première", 
                "description": "Guadeloupe Première - Actualités matinales",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 30,  # 7H00-7H30
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H Guadeloupe Première",
                "priority": 2
            }
        }
        
        # Charger le modèle Whisper (base pour l'équilibre vitesse/qualité)
        try:
            logger.info("📱 Chargement du modèle Whisper...")
            self.whisper_model = whisper.load_model("base")
            logger.info("✅ Modèle Whisper chargé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur chargement Whisper: {e}")
            self.whisper_model = None
        
        # Statuts de transcription détaillés avec étapes
        self.transcription_status = {
            "rci_7h": {
                "in_progress": False, 
                "current_step": "idle",  # idle, audio_capture, transcription, gpt_analysis, completed, error
                "step_details": "",
                "started_at": None, 
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None
            },
            "guadeloupe_premiere_7h": {
                "in_progress": False, 
                "current_step": "idle",
                "step_details": "",
                "started_at": None, 
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None
            }
        }
        
        # Nettoyer les statuts bloqués au démarrage
        self.cleanup_stale_status()

    def update_transcription_step(self, stream_key: str, step: str, details: str = "", progress: int = 0):
        """Mettre à jour l'étape actuelle de transcription"""
        if stream_key in self.transcription_status:
            self.transcription_status[stream_key]["current_step"] = step
            self.transcription_status[stream_key]["step_details"] = details
            self.transcription_status[stream_key]["progress_percentage"] = progress
            self.transcription_status[stream_key]["last_update"] = datetime.now().isoformat()
            
            # Si on commence le processus
            if step in ["audio_capture"] and not self.transcription_status[stream_key]["in_progress"]:
                self.transcription_status[stream_key]["in_progress"] = True
                self.transcription_status[stream_key]["started_at"] = datetime.now().isoformat()
                # Estimer 24h de cache
                cache_time = datetime.now() + timedelta(hours=24)
                self.transcription_status[stream_key]["cache_expires_at"] = cache_time.isoformat()
            
            # Si on termine le processus (correction importante)
            if step in ["completed", "error"]:
                self.transcription_status[stream_key]["in_progress"] = False
                self.transcription_status[stream_key]["started_at"] = None  # Nettoyer
                self.transcription_status[stream_key]["estimated_completion"] = None  # Nettoyer
                if step == "completed":
                    self.transcription_status[stream_key]["progress_percentage"] = 100
            
            stream_name = self.radio_streams[stream_key]['name']
            logger.info(f"🔄 {stream_name}: {step} - {details} ({progress}%)")

    def reset_all_transcription_status(self):
        """Remettre à zéro tous les statuts de transcription"""
        logger.info("🧹 Nettoyage des statuts de transcription...")
        for stream_key in self.transcription_status:
            self.transcription_status[stream_key] = {
                "in_progress": False,
                "current_step": "idle",
                "step_details": "",
                "started_at": None,
                "estimated_completion": None,
                "progress_percentage": 0,
                "last_update": None,
                "cache_expires_at": None
            }
        logger.info("✅ Statuts de transcription remis à zéro")

    def cleanup_stale_status(self):
        """Nettoyer les statuts bloqués (plus de 2h)"""
        from datetime import datetime, timedelta
        current_time = datetime.now()
        
        for stream_key, status in self.transcription_status.items():
            if status["in_progress"] and status["started_at"]:
                try:
                    started_time = datetime.fromisoformat(status["started_at"])
                    elapsed = current_time - started_time
                    
                    # Si le processus dure plus de 2h, c'est probablement bloqué
                    if elapsed > timedelta(hours=2):
                        logger.warning(f"🧹 Nettoyage statut bloqué pour {self.radio_streams[stream_key]['name']} (durée: {elapsed})")
                        self.update_transcription_step(stream_key, "error", "Statut expiré - nettoyé automatiquement", 0)
                except Exception as e:
                    logger.error(f"Erreur nettoyage statut {stream_key}: {e}")
                    self.update_transcription_step(stream_key, "idle", "Statut réinitialisé", 0)

    def capture_radio_stream(self, stream_key: str, duration_seconds: int) -> Optional[str]:
        """Capturer un flux radio pendant une durée donnée"""
        config = self.radio_streams[stream_key]
        
        try:
            self.update_transcription_step(stream_key, "audio_capture", f"Capture audio en cours ({duration_seconds}s)", 10)
            logger.info(f"🎵 Début capture {config['name']} pendant {duration_seconds}s...")
            
            # Créer un fichier temporaire pour l'audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Commande FFmpeg pour capturer le flux avec chemin complet
            cmd = [
                '/usr/bin/ffmpeg',
                '-i', config['url'],
                '-t', str(duration_seconds),
                '-acodec', 'mp3',
                '-ar', '16000',  # Fréquence d'échantillonnage pour Whisper
                '-ac', '1',      # Mono
                '-y',            # Overwrite
                temp_path
            ]
            
            # Exécuter la capture
            process = subprocess.run(
                cmd,
                capture_output=True,
                timeout=duration_seconds + 30,  # Timeout de sécurité
                check=True
            )
            
            # Vérifier que le fichier existe et n'est pas vide
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
                file_size = os.path.getsize(temp_path)
                self.update_transcription_step(stream_key, "transcription", f"Audio capturé ({file_size/1024:.1f}KB)", 40)
                logger.info(f"✅ Capture terminée: {file_size} bytes")
                return temp_path
            else:
                self.update_transcription_step(stream_key, "error", "Fichier audio vide", 0)
                logger.error("❌ Fichier audio vide ou inexistant")
                return None
                
        except subprocess.TimeoutExpired:
            self.update_transcription_step(stream_key, "error", "Timeout capture audio", 0)
            logger.error(f"❌ Timeout lors de la capture de {config['name']}")
            return None
        except subprocess.CalledProcessError as e:
            self.update_transcription_step(stream_key, "error", f"Erreur FFmpeg: {e}", 0)
            logger.error(f"❌ Erreur FFmpeg pour {config['name']}: {e}")
            return None
        except Exception as e:
            self.update_transcription_step(stream_key, "error", f"Erreur capture: {e}", 0)
            logger.error(f"❌ Erreur capture {config['name']}: {e}")
            return None

    def transcribe_audio_file(self, audio_path: str, stream_key: str = "unknown") -> Optional[Dict[str, Any]]:
        """Transcrire un fichier audio avec OpenAI Whisper API"""
        try:
            if stream_key != "unknown":
                self.update_transcription_step(stream_key, "transcription", "Transcription OpenAI Whisper en cours...", 60)
            logger.info(f"🎤 Début transcription OpenAI API de {os.path.basename(audio_path)}...")
            
            # Utiliser OpenAI Whisper API au lieu du modèle local
            from gpt_analysis_service import gpt_analyzer
            
            if not gpt_analyzer.client:
                logger.error("❌ Client OpenAI non disponible pour transcription")
                if stream_key != "unknown":
                    self.update_transcription_step(stream_key, "error", "Client OpenAI indisponible", 0)
                return None
                
            # Transcription avec OpenAI Whisper API
            with open(audio_path, 'rb') as audio_file:
                transcript = gpt_analyzer.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="fr"  # Français
                )
            
            transcription_data = {
                'text': transcript.text.strip(),
                'language': 'fr',
                'segments': [],  # OpenAI API ne retourne pas les segments par défaut
                'duration': 0,   # Durée non disponible via API
                'method': 'openai_whisper_api'
            }
            
            text_length = len(transcription_data['text'])
            if stream_key != "unknown":
                self.update_transcription_step(stream_key, "gpt_analysis", f"Transcription terminée ({text_length} chars)", 70)
            logger.info(f"✅ Transcription OpenAI terminée: {text_length} caractères")
            return transcription_data
            
        except Exception as e:
            logger.error(f"❌ Erreur transcription OpenAI: {e}")
            # Fallback vers Whisper local si disponible
            if hasattr(self, 'whisper_model') and self.whisper_model:
                logger.info("🔄 Fallback vers Whisper local...")
                return self._transcribe_local_fallback(audio_path, stream_key)
            else:
                if stream_key != "unknown":
                    self.update_transcription_step(stream_key, "error", f"Erreur transcription: {e}", 0)
                return None

    def _transcribe_local_fallback(self, audio_path: str, stream_key: str = "unknown") -> Optional[Dict[str, Any]]:
        """Fallback vers Whisper local si OpenAI API échoue"""
        try:
            logger.info("📱 Utilisation Whisper local en fallback...")
            if stream_key != "unknown":
                self.update_transcription_step(stream_key, "transcription", "Fallback Whisper local...", 65)
                
            result = self.whisper_model.transcribe(
                audio_path,
                language='fr',
                verbose=False
            )
            
            transcription_data = {
                'text': result['text'].strip(),
                'language': result['language'],
                'segments': [
                    {
                        'start': segment['start'],
                        'end': segment['end'], 
                        'text': segment['text'].strip()
                    }
                    for segment in result.get('segments', [])
                ],
                'duration': result.get('duration', 0),
                'method': 'whisper_local_fallback'
            }
            
            logger.info(f"✅ Transcription locale terminée: {len(transcription_data['text'])} caractères")
            return transcription_data
            
        except Exception as e:
            logger.error(f"❌ Erreur transcription locale: {e}")
            if stream_key != "unknown":
                self.update_transcription_step(stream_key, "error", f"Erreur transcription: {e}", 0)
            return None

    def set_transcription_status(self, stream_key: str, in_progress: bool, estimated_minutes: int = None):
        """Mettre à jour le statut de transcription (méthode legacy pour compatibilité)"""
        if stream_key in self.transcription_status:
            self.transcription_status[stream_key]["in_progress"] = in_progress
            
            if in_progress:
                self.transcription_status[stream_key]["started_at"] = datetime.now().isoformat()
                if estimated_minutes:
                    completion_time = datetime.now() + timedelta(minutes=estimated_minutes)
                    self.transcription_status[stream_key]["estimated_completion"] = completion_time.isoformat()
                logger.info(f"🔄 Transcription en cours: {self.radio_streams[stream_key]['name']}")
            else:
                self.transcription_status[stream_key]["started_at"] = None
                self.transcription_status[stream_key]["estimated_completion"] = None
                logger.info(f"✅ Transcription terminée: {self.radio_streams[stream_key]['name']}")

    def get_transcription_status(self) -> Dict[str, Any]:
        """Récupérer le statut détaillé de toutes les transcriptions"""
        status_summary = {
            "sections": {},
            "global_status": {
                "any_in_progress": False,
                "total_sections": len(self.radio_streams),
                "active_sections": 0
            }
        }
        
        for stream_key, config in self.radio_streams.items():
            section_status = self.transcription_status[stream_key].copy()
            section_status.update({
                "section_name": config["section"],
                "description": config["description"],
                "duration_minutes": config["duration_minutes"],
                "start_time": f"{config['start_hour']:02d}:{config['start_minute']:02d}",
                "priority": config["priority"]
            })
            
            # Ajouter des statuts plus lisibles
            step_descriptions = {
                "idle": "En attente",
                "audio_capture": "📻 Capture audio en cours",
                "transcription": "🎤 Transcription en cours",
                "gpt_analysis": "🧠 Analyse GPT en cours",
                "completed": "✅ Terminé",
                "error": "❌ Erreur"
            }
            
            section_status["step_description"] = step_descriptions.get(
                section_status["current_step"], 
                section_status["current_step"]
            )
            
            status_summary["sections"][stream_key] = section_status
            
            if section_status["in_progress"]:
                status_summary["global_status"]["any_in_progress"] = True
                status_summary["global_status"]["active_sections"] += 1
        
        return status_summary

    def get_todays_transcriptions_by_section(self) -> Dict[str, List]:
        """Récupérer les transcriptions d'aujourd'hui organisées par section"""
        today = datetime.now().strftime('%Y-%m-%d')
        all_transcriptions = list(self.transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        sections = {
            "7H RCI": [],
            "7H Guadeloupe Première": [],
            "Autres": []
        }
        
        for transcription in all_transcriptions:
            section = transcription.get('section', 'Autres')
            if section in sections:
                sections[section].append(transcription)
            else:
                sections["Autres"].append(transcription)
        
        return sections

    def capture_and_transcribe_stream(self, stream_key: str) -> Dict[str, Any]:
        """Capturer et transcrire un flux radio avec analyse GPT"""
        config = self.radio_streams[stream_key]
        duration_seconds = config['duration_minutes'] * 60
        
        result = {
            'success': False,
            'stream_key': stream_key,
            'stream_name': config['name'],
            'section': config['section'],
            'timestamp': datetime.now().isoformat(),
            'error': None,
            'transcription': None
        }
        
        try:
            # Marquer comme en cours
            self.update_transcription_step(stream_key, "audio_capture", "Initialisation...", 5)
            
            # 1. Capturer le flux
            audio_path = self.capture_radio_stream(stream_key, duration_seconds)
            if not audio_path:
                result['error'] = "Échec de la capture audio"
                return result
            
            try:
                # 2. Transcrire l'audio
                transcription = self.transcribe_audio_file(audio_path, stream_key)
                if not transcription:
                    result['error'] = "Échec de la transcription"
                    return result
                
                # 3. Analyse intelligente avec GPT-4.1-mini
                self.update_transcription_step(stream_key, "gpt_analysis", "Analyse GPT en cours...", 80)
                logger.info("🧠 Analyse GPT de la transcription...")
                
                try:
                    from gpt_analysis_service import analyze_transcription_with_gpt
                    gpt_analysis = analyze_transcription_with_gpt(transcription['text'], config['name'])
                except ImportError:
                    logger.warning("Service GPT non disponible, utilisation du fallback local")
                    from transcription_analysis_service import analyze_transcription
                    gpt_analysis = analyze_transcription(transcription['text'], config['name'])
                
                self.update_transcription_step(stream_key, "completed", "Sauvegarde en cours...", 95)
                
                # 4. Sauvegarder en base de données avec analyse GPT
                transcription_record = {
                    'id': f"{stream_key}_{int(time.time())}",
                    'stream_key': stream_key,
                    'stream_name': config['name'],
                    'section': config['section'],
                    'description': config['description'],
                    'stream_url': config['url'],
                    
                    # Transcription brute
                    'transcription_text': transcription['text'],
                    'language': transcription['language'],
                    'duration_seconds': transcription['duration'],
                    'segments': transcription['segments'],
                    
                    # Analyse GPT
                    'gpt_analysis': gpt_analysis.get('gpt_analysis', gpt_analysis.get('summary', '')),
                    'ai_summary': gpt_analysis.get('gpt_analysis', gpt_analysis.get('summary', '')),
                    'analysis_method': gpt_analysis.get('analysis_method', 'gpt-4o-mini'),
                    'analysis_status': gpt_analysis.get('status', 'success'),
                    'ai_analysis_metadata': gpt_analysis.get('analysis_metadata', {}),
                    
                    # Compatibilité avec ancien format
                    'ai_key_sentences': gpt_analysis.get('key_sentences', []),
                    'ai_main_topics': gpt_analysis.get('main_topics', []),
                    'ai_keywords': gpt_analysis.get('keywords', []),
                    'ai_relevance_score': gpt_analysis.get('relevance_score', 0.8),
                    
                    # Métadonnées
                    'captured_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'audio_size_bytes': os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
                    'priority': config['priority'],
                    'start_time': f"{config['start_hour']:02d}:{config['start_minute']:02d}"
                }
                
                # Insérer en base
                record_for_db = transcription_record.copy()
                insert_result = self.transcriptions_collection.insert_one(record_for_db)
                
                # Le record original n'a pas d'ObjectId ajouté par MongoDB
                result['success'] = True
                result['transcription'] = transcription_record
                
                self.update_transcription_step(stream_key, "completed", "✅ Terminé avec succès", 100)
                logger.info(f"✅ Transcription sauvegardée pour {config['section']}")
                
            finally:
                # Nettoyer le fichier temporaire
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
                    
        except Exception as e:
            result['error'] = str(e)
            self.update_transcription_step(stream_key, "error", f"Erreur: {str(e)}", 0)
            logger.error(f"❌ Erreur globale pour {config['section']}: {e}")
        
        return result

    def capture_radio_stream(self, stream_key: str, duration_seconds: int) -> Optional[str]:
        """Capturer un flux radio pendant une durée donnée"""
        config = self.radio_streams[stream_key]
        
        try:
            logger.info(f"🎵 Début capture {config['name']} pendant {duration_seconds}s...")
            
            # Créer un fichier temporaire pour l'audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Commande FFmpeg pour capturer le flux avec chemin complet
            cmd = [
                '/usr/bin/ffmpeg',
                '-i', config['url'],
                '-t', str(duration_seconds),
                '-acodec', 'mp3',
                '-ar', '16000',  # Fréquence d'échantillonnage pour Whisper
                '-ac', '1',      # Mono
                '-y',            # Overwrite
                temp_path
            ]
            
            # Exécuter la capture
            process = subprocess.run(
                cmd,
                capture_output=True,
                timeout=duration_seconds + 30,  # Timeout de sécurité
                check=True
            )
            
            # Vérifier que le fichier existe et n'est pas vide
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
                logger.info(f"✅ Capture terminée: {os.path.getsize(temp_path)} bytes")
                return temp_path
            else:
                logger.error("❌ Fichier audio vide ou inexistant")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Timeout lors de la capture de {config['name']}")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Erreur FFmpeg pour {config['name']}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Erreur capture {config['name']}: {e}")
            return None

    def set_transcription_status(self, stream_key: str, in_progress: bool, estimated_minutes: int = None):
        """Mettre à jour le statut de transcription"""
        if stream_key in self.transcription_status:
            self.transcription_status[stream_key]["in_progress"] = in_progress
            
            if in_progress:
                self.transcription_status[stream_key]["started_at"] = datetime.now().isoformat()
                if estimated_minutes:
                    completion_time = datetime.now() + timedelta(minutes=estimated_minutes)
                    self.transcription_status[stream_key]["estimated_completion"] = completion_time.isoformat()
                logger.info(f"🔄 Transcription en cours: {self.radio_streams[stream_key]['name']}")
            else:
                self.transcription_status[stream_key]["started_at"] = None
                self.transcription_status[stream_key]["estimated_completion"] = None
                logger.info(f"✅ Transcription terminée: {self.radio_streams[stream_key]['name']}")

    def get_transcription_status(self) -> Dict[str, Any]:
        """Récupérer le statut de toutes les transcriptions"""
        status_summary = {
            "sections": {},
            "global_status": {
                "any_in_progress": False,
                "total_sections": len(self.radio_streams),
                "active_sections": 0
            }
        }
        
        for stream_key, config in self.radio_streams.items():
            section_status = self.transcription_status[stream_key].copy()
            section_status.update({
                "section_name": config["section"],
                "description": config["description"],
                "duration_minutes": config["duration_minutes"],
                "start_time": f"{config['start_hour']:02d}:{config['start_minute']:02d}",
                "priority": config["priority"]
            })
            
            status_summary["sections"][stream_key] = section_status
            
            if section_status["in_progress"]:
                status_summary["global_status"]["any_in_progress"] = True
                status_summary["global_status"]["active_sections"] += 1
        
        return status_summary

    def get_todays_transcriptions_by_section(self) -> Dict[str, List]:
        """Récupérer les transcriptions d'aujourd'hui organisées par section"""
        today = datetime.now().strftime('%Y-%m-%d')
        all_transcriptions = list(self.transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        sections = {
            "7H RCI": [],
            "7H Guadeloupe Première": [],
            "Autres": []
        }
        
        for transcription in all_transcriptions:
            section = transcription.get('section', 'Autres')
            if section in sections:
                sections[section].append(transcription)
            else:
                sections["Autres"].append(transcription)
        
        return sections

    def capture_and_transcribe_stream(self, stream_key: str) -> Dict[str, Any]:
        """Capturer et transcrire un flux radio"""
        config = self.radio_streams[stream_key]
        duration_seconds = config['duration_minutes'] * 60
        
        result = {
            'success': False,
            'stream_key': stream_key,
            'stream_name': config['name'],
            'section': config['section'],
            'timestamp': datetime.now().isoformat(),
            'error': None,
            'transcription': None
        }
        
        try:
            # Marquer comme en cours avec la nouvelle méthode
            self.update_transcription_step(stream_key, "audio_capture", "Initialisation...", 5)
            
            # 1. Capturer le flux
            audio_path = self.capture_radio_stream(stream_key, duration_seconds)
            if not audio_path:
                result['error'] = "Échec de la capture audio"
                return result
            
            try:
                # 2. Transcrire l'audio
                transcription = self.transcribe_audio_file(audio_path)
                if not transcription:
                    result['error'] = "Échec de la transcription"
                    return result
                
                # 3. Analyse intelligente de la transcription
                logger.info("🧠 Analyse intelligente de la transcription...")
                from transcription_analysis_service import analyze_transcription
                analysis = analyze_transcription(transcription['text'], config['name'])
                
                # 4. Sauvegarder en base de données avec analyse
                transcription_record = {
                    'id': f"{stream_key}_{int(time.time())}",
                    'stream_key': stream_key,
                    'stream_name': config['name'],
                    'section': config['section'],
                    'description': config['description'],
                    'stream_url': config['url'],
                    
                    # Transcription brute
                    'transcription_text': transcription['text'],
                    'language': transcription['language'],
                    'duration_seconds': transcription['duration'],
                    'segments': transcription['segments'],
                    
                    # Analyse intelligente
                    'ai_summary': analysis.get('summary', transcription['text']),
                    'ai_key_sentences': analysis.get('key_sentences', []),
                    'ai_main_topics': analysis.get('main_topics', []),
                    'ai_keywords': analysis.get('keywords', []),
                    'ai_relevance_score': analysis.get('relevance_score', 0.5),
                    'ai_analysis_metadata': analysis.get('analysis_metadata', {}),
                    
                    # Métadonnées
                    'captured_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'audio_size_bytes': os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
                    'priority': config['priority'],
                    'start_time': f"{config['start_hour']:02d}:{config['start_minute']:02d}"
                }
                
                # Insérer en base
                record_for_db = transcription_record.copy()
                insert_result = self.transcriptions_collection.insert_one(record_for_db)
                
                # Le record original n'a pas d'ObjectId ajouté par MongoDB
                result['success'] = True
                result['transcription'] = transcription_record
                
                logger.info(f"✅ Transcription sauvegardée pour {config['section']}")
                
            finally:
                # Nettoyer le fichier temporaire
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
                    
        except Exception as e:
            result['error'] = str(e)  
            self.update_transcription_step(stream_key, "error", f"Erreur globale: {str(e)}", 0)
            logger.error(f"❌ Erreur globale pour {config['section']}: {e}")
        
        return result

    def capture_all_streams(self) -> Dict[str, Any]:
        """Capturer et transcrire tous les flux radio"""
        logger.info("🚀 Début capture de tous les flux radio...")
        
        results = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'streams_processed': 0,
            'streams_success': 0,
            'transcriptions': [],
            'errors': []
        }
        
        # Capturer les flux en parallèle
        threads = []
        stream_results = {}
        
        def capture_stream(stream_key):
            stream_results[stream_key] = self.capture_and_transcribe_stream(stream_key)
        
        # Lancer les captures en parallèle
        for stream_key in self.radio_streams.keys():
            thread = threading.Thread(target=capture_stream, args=(stream_key,))
            threads.append(thread)
            thread.start()
        
        # Attendre la fin de toutes les captures
        for thread in threads:
            thread.join()
        
        # Compiler les résultats
        for stream_key, stream_result in stream_results.items():
            results['streams_processed'] += 1
            
            if stream_result['success']:
                results['streams_success'] += 1
                results['transcriptions'].append(stream_result['transcription'])
            else:
                results['errors'].append(f"{stream_result['stream_name']}: {stream_result['error']}")
        
        results['success'] = results['streams_success'] > 0
        
        logger.info(f"📊 Capture terminée: {results['streams_success']}/{results['streams_processed']} flux réussis")
        
        return results

    def get_todays_transcriptions(self) -> list:
        """Récupérer les transcriptions d'aujourd'hui"""
        today = datetime.now().strftime('%Y-%m-%d')
        transcriptions = list(self.transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        return transcriptions

    def get_transcriptions_by_date(self, date_str: str) -> list:
        """Récupérer les transcriptions d'une date spécifique"""
        transcriptions = list(self.transcriptions_collection.find(
            {'date': date_str}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        return transcriptions

# Instance globale du service radio
radio_service = RadioTranscriptionService()

def run_morning_radio_capture():
    """Fonction pour lancer la capture matinale à 7H"""
    logger.info("⏰ Lancement de la capture radio matinale à 7H")
    return radio_service.capture_all_streams()

if __name__ == "__main__":
    # Test du service
    result = radio_service.capture_all_streams()
    print(f"Résultat: {result}")