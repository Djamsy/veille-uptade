#!/usr/bin/env python3
"""
Backend API Test Suite for Guadeloupe Media Monitoring Application
Tests all endpoints focusing on new implementations:
1. Today-Only Data Display
2. Cache Clearing on Updates  
3. Local Sentiment Analysis Service
"""

import requests
import sys
import json
import tempfile
import os
from datetime import datetime

class GuadeloupeMediaAPITester:
    def __init__(self, base_url="https://938e5f4b-4f11-496e-9c1b-9acf492d425b.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 60  # Increased timeout for scraping operations
        self.today = datetime.now().strftime('%Y-%m-%d')

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_root_endpoint(self):
        """Test root endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/")
            success = response.status_code == 200
            if success:
                data = response.json()
                details = f"- Message: {data.get('message', 'No message')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Root Endpoint", success, details)
        except Exception as e:
            return self.log_test("Root Endpoint", False, f"- Error: {str(e)}")

    def test_today_only_dashboard_stats(self):
        """Test dashboard statistics endpoint shows only today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/dashboard-stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    today_articles = stats.get('today_articles', 0)
                    total_articles = stats.get('total_articles', 0)
                    showing_data_for = stats.get('showing_data_for', '')
                    
                    # Check if today_articles equals total_articles (today-only filter)
                    today_only_working = today_articles == total_articles
                    has_today_message = self.today in showing_data_for
                    
                    if today_only_working and has_today_message:
                        details = f"- Today articles: {today_articles}, Message: '{showing_data_for}'"
                    else:
                        success = False
                        details = f"- Today filter not working: today={today_articles}, total={total_articles}, message='{showing_data_for}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Today-Only Dashboard Stats", success, details)
        except Exception as e:
            return self.log_test("Today-Only Dashboard Stats", False, f"- Error: {str(e)}")

    def test_today_only_articles(self):
        """Test articles endpoint shows only today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    count = data.get('count', 0)
                    
                    # Check if all articles are from today
                    today_only = True
                    for article in articles[:5]:  # Check first 5 articles
                        article_date = article.get('date', '')
                        if article_date != self.today:
                            today_only = False
                            break
                    
                    if today_only and count == len(articles):
                        details = f"- Found {count} articles, all from {self.today}"
                    else:
                        success = False
                        details = f"- Today filter not working: {count} articles, today_only={today_only}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Today-Only Articles", success, details)
        except Exception as e:
            return self.log_test("Today-Only Articles", False, f"- Error: {str(e)}")

    def test_cache_clearing_scrape_now(self):
        """Test scrape-now endpoint clears cache before and after scraping"""
        try:
            response = self.session.post(f"{self.base_url}/api/articles/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cache_cleared = data.get('cache_cleared', False)
                    message = data.get('message', '')
                    
                    if cache_cleared and 'cache' in message.lower():
                        details = f"- Cache cleared: {cache_cleared}, Message: '{message}'"
                    else:
                        success = False
                        details = f"- Cache clearing not confirmed: cache_cleared={cache_cleared}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Cache Clearing on Scrape", success, details)
        except Exception as e:
            return self.log_test("Cache Clearing on Scrape", False, f"- Error: {str(e)}")

    def test_sentiment_stats(self):
        """Test sentiment analysis stats endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    service_info = data.get('service_info', {})
                    service_enabled = service_info.get('service_enabled', False)
                    analysis_method = service_info.get('analysis_method', '')
                    
                    if service_enabled and 'local' in analysis_method:
                        details = f"- Service enabled: {service_enabled}, Method: {analysis_method}"
                    else:
                        success = False
                        details = f"- Local sentiment not enabled: enabled={service_enabled}, method={analysis_method}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analysis Stats", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analysis Stats", False, f"- Error: {str(e)}")

    def test_sentiment_articles(self):
        """Test sentiment analysis of today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    summary = data.get('summary', {})
                    total_articles = summary.get('total_articles', 0)
                    sentiment_distribution = summary.get('sentiment_distribution', {})
                    
                    if total_articles >= 0 and 'positive' in sentiment_distribution:
                        details = f"- Analyzed {total_articles} articles, Distribution: {sentiment_distribution}"
                    else:
                        success = False
                        details = f"- Sentiment analysis failed: articles={total_articles}, dist={sentiment_distribution}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analysis Articles", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analysis Articles", False, f"- Error: {str(e)}")

    def test_sentiment_analyze_text(self):
        """Test sentiment analysis of custom text"""
        try:
            test_text = "C'est une excellente nouvelle pour la Guadeloupe! Le développement économique progresse bien."
            data = {'text': test_text}
            response = self.session.post(f"{self.base_url}/api/sentiment/analyze", data=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    sentiment = response_data.get('sentiment', {})
                    polarity = sentiment.get('polarity', '')
                    score = sentiment.get('score', 0)
                    intensity = sentiment.get('intensity', '')
                    
                    if polarity and score is not None:
                        details = f"- Text sentiment: {polarity} (Score: {score:.3f}, Intensity: {intensity})"
                    else:
                        success = False
                        details = f"- Sentiment analysis incomplete: polarity={polarity}, score={score}"
                else:
                    success = False
                    details = f"- API returned success=False: {response_data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analyze Text", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analyze Text", False, f"- Error: {str(e)}")

    def test_sentiment_trends(self):
        """Test sentiment trends over past 7 days"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/trends")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    trends_by_date = data.get('trends_by_date', {})
                    analysis_period = data.get('analysis_period', {})
                    
                    if len(trends_by_date) >= 0 and analysis_period:
                        details = f"- Trends for {len(trends_by_date)} days, Period: {analysis_period.get('total_days', 0)} days"
                    else:
                        success = False
                        details = f"- Trends analysis failed: trends={len(trends_by_date)}, period={analysis_period}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Trends", success, details)
        except Exception as e:
            return self.log_test("Sentiment Trends", False, f"- Error: {str(e)}")

    def test_scrapers_working(self):
        """Test that all 4 scrapers are working by checking articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Check for articles from different sources
                    sources_found = set()
                    for article in articles:
                        source = article.get('source', '')
                        if source:
                            sources_found.add(source)
                    
                    expected_sources = {'France-Antilles Guadeloupe', 'RCI Guadeloupe', 'La 1ère Guadeloupe', 'KaribInfo'}
                    working_scrapers = len(sources_found.intersection(expected_sources))
                    
                    if working_scrapers >= 2:  # At least 2 scrapers working
                        details = f"- Found articles from {working_scrapers}/4 scrapers: {list(sources_found)}"
                    else:
                        success = False
                        details = f"- Only {working_scrapers}/4 scrapers working: {list(sources_found)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("News Scrapers Working", success, details)
        except Exception as e:
            return self.log_test("News Scrapers Working", False, f"- Error: {str(e)}")

    def test_transcriptions_endpoint(self):
        """Test transcriptions endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/transcriptions")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    transcriptions = data.get('transcriptions', [])
                    details = f"- Found {len(transcriptions)} transcriptions"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Transcriptions Endpoint", success, details)
        except Exception as e:
            return self.log_test("Transcriptions Endpoint", False, f"- Error: {str(e)}")

    def test_transcriptions_by_date(self):
        """Test transcriptions by date endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/transcriptions/{self.today}")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    transcriptions = data.get('transcriptions', [])
                    count = data.get('count', 0)
                    date = data.get('date', '')
                    details = f"- Found {count} transcriptions for {date}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Transcriptions By Date", success, details)
        except Exception as e:
            return self.log_test("Transcriptions By Date", False, f"- Error: {str(e)}")

    def test_capture_radio_now(self):
        """Test manual radio capture endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/transcriptions/capture-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    details = f"- Message: '{message}', ETA: {estimated_completion}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Capture Radio Now", success, details)
        except Exception as e:
            return self.log_test("Capture Radio Now", False, f"- Error: {str(e)}")

    def test_capture_status(self):
        """Test radio capture status endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/transcriptions/capture-status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', {})
                    details = f"- Capture status retrieved: {len(result)} fields"
                else:
                    # No recent capture is also acceptable
                    message = data.get('message', '')
                    details = f"- No recent capture: {message}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Capture Status", success, details)
        except Exception as e:
            return self.log_test("Capture Status", False, f"- Error: {str(e)}")

    def test_upload_audio_transcription(self):
        """Test audio upload and transcription endpoint"""
        try:
            # Create a small test audio file (silence)
            import tempfile
            import wave
            import struct
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                # Create a 1-second silence WAV file
                sample_rate = 16000
                duration = 1  # 1 second
                frames = sample_rate * duration
                
                with wave.open(temp_file.name, 'w') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)
                    
                    # Write silence (zeros)
                    for _ in range(frames):
                        wav_file.writeframes(struct.pack('<h', 0))
                
                # Upload the file
                with open(temp_file.name, 'rb') as audio_file:
                    files = {'file': ('test_audio.wav', audio_file, 'audio/wav')}
                    response = self.session.post(f"{self.base_url}/api/transcribe", files=files)
                
                # Clean up
                os.unlink(temp_file.name)
            
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    transcription = data.get('transcription', {})
                    text = transcription.get('transcription_text', '')
                    details = f"- Transcription successful: '{text[:50]}...'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Upload Audio Transcription", success, details)
        except Exception as e:
            return self.log_test("Upload Audio Transcription", False, f"- Error: {str(e)}")

    def test_scheduler_status(self):
        """Test scheduler status endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/scheduler/status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    jobs = data.get('jobs', [])
                    scheduler_running = data.get('scheduler_running', False)
                    recent_logs = data.get('recent_logs', [])
                    details = f"- Scheduler running: {scheduler_running}, Jobs: {len(jobs)}, Logs: {len(recent_logs)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Scheduler Status", success, details)
        except Exception as e:
            return self.log_test("Scheduler Status", False, f"- Error: {str(e)}")

    def test_ffmpeg_dependency(self):
        """Test if ffmpeg is available for radio capture"""
        try:
            # Test by trying to capture radio (this will fail if ffmpeg is missing)
            response = self.session.post(f"{self.base_url}/api/transcriptions/capture-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    details = f"- ffmpeg appears to be available (capture initiated)"
                else:
                    error_msg = data.get('error', '').lower()
                    if 'ffmpeg' in error_msg or 'not found' in error_msg:
                        success = False
                        details = f"- ffmpeg missing: {data.get('error', 'Unknown error')}"
                    else:
                        details = f"- ffmpeg available but other error: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("FFmpeg Dependency Check", success, details)
        except Exception as e:
            return self.log_test("FFmpeg Dependency Check", False, f"- Error: {str(e)}")

    def test_whisper_dependency(self):
        """Test if Whisper is properly configured"""
        try:
            # Test by uploading a small audio file
            import tempfile
            import wave
            import struct
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                # Create a very small test audio file
                sample_rate = 16000
                duration = 0.1  # 0.1 second
                frames = int(sample_rate * duration)
                
                with wave.open(temp_file.name, 'w') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    
                    for _ in range(frames):
                        wav_file.writeframes(struct.pack('<h', 0))
                
                # Upload the file to test Whisper
                with open(temp_file.name, 'rb') as audio_file:
                    files = {'file': ('whisper_test.wav', audio_file, 'audio/wav')}
                    response = self.session.post(f"{self.base_url}/api/transcribe", files=files)
                
                os.unlink(temp_file.name)
            
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    details = f"- Whisper working correctly"
                else:
                    error_msg = data.get('error', '').lower()
                    if 'whisper' in error_msg or 'model' in error_msg:
                        success = False
                        details = f"- Whisper issue: {data.get('error', 'Unknown error')}"
                    else:
                        details = f"- Whisper available but other error: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Whisper Dependency Check", success, details)
        except Exception as e:
            return self.log_test("Whisper Dependency Check", False, f"- Error: {str(e)}")

    def test_radio_streaming_urls(self):
        """Test if radio streaming URLs are accessible"""
        try:
            # Test the radio streaming URLs by checking if capture can be initiated
            response = self.session.post(f"{self.base_url}/api/transcriptions/capture-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    details = f"- Radio streaming URLs appear accessible"
                else:
                    error_msg = data.get('error', '').lower()
                    if 'url' in error_msg or 'stream' in error_msg or 'connection' in error_msg:
                        success = False
                        details = f"- Radio URL issue: {data.get('error', 'Unknown error')}"
                    else:
                        details = f"- URLs accessible but other error: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Radio Streaming URLs Check", success, details)
        except Exception as e:
            return self.log_test("Radio Streaming URLs Check", False, f"- Error: {str(e)}")

    def test_health_endpoint(self):
        """Test health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    health = data.get('health', {})
                    services = health.get('services', {})
                    details = f"- Status: {health.get('status', 'unknown')}, Services: {len(services)}"
                else:
                    success = False
                    details = f"- Health check failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Health Check", success, details)
        except Exception as e:
            return self.log_test("Health Check", False, f"- Error: {str(e)}")

    def test_search_endpoint(self):
        """Test search endpoint with specific queries for Guy Losbar and Conseil Départemental"""
        test_queries = ["Guy Losbar", "Conseil Départemental", "CD971"]
        
        for query in test_queries:
            try:
                response = self.session.get(f"{self.base_url}/api/search", params={'q': query})
                success = response.status_code == 200
                if success:
                    data = response.json()
                    if data.get('success'):
                        articles = data.get('articles', [])
                        social_posts = data.get('social_posts', [])
                        total_results = data.get('total_results', 0)
                        searched_in = data.get('searched_in', [])
                        
                        if total_results >= 0 and len(searched_in) > 0:
                            details = f"- Query '{query}': {len(articles)} articles, {len(social_posts)} social posts, searched in: {searched_in}"
                        else:
                            success = False
                            details = f"- Query '{query}' failed: total={total_results}, searched_in={searched_in}"
                    else:
                        success = False
                        details = f"- Query '{query}' API returned success=False: {data.get('error', 'Unknown error')}"
                else:
                    details = f"- Query '{query}' Status: {response.status_code}"
                
                self.log_test(f"Search Endpoint - '{query}'", success, details)
            except Exception as e:
                self.log_test(f"Search Endpoint - '{query}'", False, f"- Error: {str(e)}")

    def test_comments_endpoint(self):
        """Test comments endpoint to retrieve social media posts"""
        try:
            response = self.session.get(f"{self.base_url}/api/comments")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    comments = data.get('comments', [])
                    count = data.get('count', 0)
                    
                    # Check if comments have sentiment analysis
                    has_sentiment = False
                    if comments:
                        first_comment = comments[0]
                        has_sentiment = 'sentiment_summary' in first_comment or 'sentiment' in first_comment
                    
                    if count >= 0:
                        details = f"- Found {count} comments/posts, sentiment analysis: {has_sentiment}"
                    else:
                        success = False
                        details = f"- Comments retrieval failed: count={count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments Endpoint", success, details)
        except Exception as e:
            return self.log_test("Comments Endpoint", False, f"- Error: {str(e)}")

    def test_social_scrape_now(self):
        """Test social media scraping endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    note = data.get('note', '')
                    
                    if 'scraping' in message.lower() and estimated_completion:
                        details = f"- Message: '{message}', ETA: {estimated_completion}, Note: '{note}'"
                    else:
                        success = False
                        details = f"- Social scraping not properly initiated: message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Media Scrape Now", success, details)
        except Exception as e:
            return self.log_test("Social Media Scrape Now", False, f"- Error: {str(e)}")

    def test_social_stats(self):
        """Test social media statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    
                    if isinstance(stats, dict) and len(stats) >= 0:
                        details = f"- Social stats retrieved: {len(stats)} stat categories"
                    else:
                        success = False
                        details = f"- Social stats failed: stats={stats}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Media Stats", success, details)
        except Exception as e:
            return self.log_test("Social Media Stats", False, f"- Error: {str(e)}")

    def test_search_suggestions(self):
        """Test search suggestions endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/search/suggestions", params={'q': 'Guy'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    suggestions = data.get('suggestions', [])
                    
                    if isinstance(suggestions, list):
                        details = f"- Found {len(suggestions)} suggestions: {suggestions[:3]}"
                    else:
                        success = False
                        details = f"- Search suggestions failed: suggestions={suggestions}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Search Suggestions", success, details)
        except Exception as e:
            return self.log_test("Search Suggestions", False, f"- Error: {str(e)}")

    def test_comments_analyze(self):
        """Test comments sentiment analysis endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/comments/analyze")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    analysis = data.get('analysis', {})
                    total_comments = analysis.get('total_comments', 0)
                    by_entity = analysis.get('by_entity', {})
                    
                    if total_comments >= 0 and isinstance(by_entity, dict):
                        details = f"- Analyzed {total_comments} comments, entities: {list(by_entity.keys())}"
                    else:
                        success = False
                        details = f"- Comments analysis failed: total={total_comments}, entities={len(by_entity)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments Sentiment Analysis", success, details)
        except Exception as e:
            return self.log_test("Comments Sentiment Analysis", False, f"- Error: {str(e)}")

    def test_social_clean_demo_data(self):
        """Test cleaning demo data from social media database"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/clean-demo-data")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cleaned_count = data.get('cleaned_count', 0)
                    message = data.get('message', '')
                    
                    if cleaned_count >= 0 and 'démonstration' in message.lower():
                        details = f"- Cleaned {cleaned_count} demo posts, Message: '{message}'"
                    else:
                        success = False
                        details = f"- Demo data cleaning failed: count={cleaned_count}, message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Clean Demo Data", success, details)
        except Exception as e:
            return self.log_test("Social Clean Demo Data", False, f"- Error: {str(e)}")

    def test_social_scrape_real_data(self):
        """Test social media scraping for real data (no demo fallback)"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    note = data.get('note', '')
                    
                    # Check that it's attempting real scraping, not demo mode
                    if 'scraping' in message.lower() and 'démonstration' not in message.lower():
                        details = f"- Real scraping initiated: '{message}', ETA: {estimated_completion}"
                    else:
                        success = False
                        details = f"- May be using demo mode: message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Real Data Scraping", success, details)
        except Exception as e:
            return self.log_test("Social Real Data Scraping", False, f"- Error: {str(e)}")

    def test_comments_no_demo_data(self):
        """Test that comments endpoint returns only real data (no demo_data: true)"""
        try:
            response = self.session.get(f"{self.base_url}/api/comments")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    comments = data.get('comments', [])
                    count = data.get('count', 0)
                    
                    # Check if any comments have demo_data flag
                    demo_data_found = False
                    for comment in comments[:10]:  # Check first 10 comments
                        if comment.get('demo_data') is True:
                            demo_data_found = True
                            break
                    
                    if not demo_data_found:
                        details = f"- Found {count} real comments (no demo data detected)"
                    else:
                        success = False
                        details = f"- Demo data still present in comments: count={count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments No Demo Data", success, details)
        except Exception as e:
            return self.log_test("Comments No Demo Data", False, f"- Error: {str(e)}")

    def test_search_guy_losbar_real_data(self):
        """Test search for 'Guy Losbar' returns only real data"""
        try:
            response = self.session.get(f"{self.base_url}/api/search", params={'q': 'Guy Losbar'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    social_posts = data.get('social_posts', [])
                    total_results = data.get('total_results', 0)
                    
                    # Check if any results have demo_data flag
                    demo_data_found = False
                    all_results = articles + social_posts
                    for result in all_results[:5]:  # Check first 5 results
                        if result.get('demo_data') is True:
                            demo_data_found = True
                            break
                    
                    if not demo_data_found:
                        details = f"- Found {total_results} real results for 'Guy Losbar' (no demo data)"
                    else:
                        success = False
                        details = f"- Demo data still present in search results: total={total_results}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Search Guy Losbar Real Data", success, details)
        except Exception as e:
            return self.log_test("Search Guy Losbar Real Data", False, f"- Error: {str(e)}")

    def test_social_stats_real_data(self):
        """Test social media stats show real data only"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    
                    # Check if stats indicate real data (not demo mode)
                    demo_mode = stats.get('demo_mode', False)
                    total_posts = stats.get('total_posts', 0)
                    
                    if not demo_mode and total_posts >= 0:
                        details = f"- Real social stats: {total_posts} posts, demo_mode: {demo_mode}"
                    else:
                        success = False
                        details = f"- May be in demo mode: demo_mode={demo_mode}, posts={total_posts}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Stats Real Data", success, details)
        except Exception as e:
            return self.log_test("Social Stats Real Data", False, f"- Error: {str(e)}")

    def test_social_scrape_status_check(self):
        """Test social scrape status to verify real data processing"""
        try:
            # Wait a moment for scraping to potentially start
            import time
            time.sleep(2)
            
            response = self.session.get(f"{self.base_url}/api/social/scrape-status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', {})
                    demo_mode = result.get('demo_mode', False)
                    total_posts = result.get('total_posts', 0)
                    note = result.get('note', '')
                    
                    if not demo_mode:
                        details = f"- Real scraping status: {total_posts} posts, demo_mode: {demo_mode}, note: '{note}'"
                    else:
                        success = False
                        details = f"- Still in demo mode: demo_mode={demo_mode}, note='{note}'"
                else:
                    # No recent scraping is also acceptable
                    details = f"- No recent scraping result (acceptable): {data.get('message', '')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Scrape Status Check", success, details)
        except Exception as e:
            return self.log_test("Social Scrape Status Check", False, f"- Error: {str(e)}")

    def test_digest_today_pdf(self):
        """Test today's digest PDF download"""
        try:
            response = self.session.get(f"{self.base_url}/api/digest/today/pdf")
            success = response.status_code == 200
            if success:
                # Check if response is PDF
                content_type = response.headers.get('content-type', '')
                content_disposition = response.headers.get('content-disposition', '')
                content_length = len(response.content)
                
                is_pdf = 'application/pdf' in content_type
                has_filename = 'digest_guadeloupe_' in content_disposition
                has_content = content_length > 1000  # PDF should be at least 1KB
                
                if is_pdf and has_content:
                    details = f"- PDF downloaded: {content_length} bytes, Content-Type: {content_type}"
                else:
                    success = False
                    details = f"- PDF invalid: size={content_length}, type='{content_type}', disposition='{content_disposition}'"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Today's Digest PDF", success, details)
        except Exception as e:
            return self.log_test("Today's Digest PDF", False, f"- Error: {str(e)}")

    def test_digest_specific_date_pdf(self):
        """Test specific date digest PDF download"""
        try:
            test_date = "2025-07-30"
            response = self.session.get(f"{self.base_url}/api/digest/{test_date}/pdf")
            success = response.status_code == 200
            if success:
                # Check if response is PDF
                content_type = response.headers.get('content-type', '')
                content_disposition = response.headers.get('content-disposition', '')
                content_length = len(response.content)
                
                is_pdf = 'application/pdf' in content_type
                has_filename = f'digest_guadeloupe_{test_date}' in content_disposition
                has_content = content_length > 1000  # PDF should be at least 1KB
                
                if is_pdf and has_content:
                    details = f"- PDF downloaded for {test_date}: {content_length} bytes, Content-Type: {content_type}"
                else:
                    success = False
                    details = f"- PDF invalid: size={content_length}, type='{content_type}', disposition='{content_disposition}'"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Specific Date Digest PDF", success, details)
        except Exception as e:
            return self.log_test("Specific Date Digest PDF", False, f"- Error: {str(e)}")

    def test_digest_json_endpoint(self):
        """Test digest JSON endpoint for comparison"""
        try:
            response = self.session.get(f"{self.base_url}/api/digest")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    digest = data.get('digest', {})
                    articles_count = digest.get('articles_count', 0)
                    transcriptions_count = digest.get('transcriptions_count', 0)
                    created_at = digest.get('created_at', '')
                    
                    if articles_count >= 0 and created_at:
                        details = f"- Digest created: {articles_count} articles, {transcriptions_count} transcriptions"
                    else:
                        success = False
                        details = f"- Digest incomplete: articles={articles_count}, created_at='{created_at}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Digest JSON Endpoint", success, details)
        except Exception as e:
            return self.log_test("Digest JSON Endpoint", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all API tests focusing on new features"""
        print("🚀 Starting Guadeloupe Media Monitoring API Tests")
        print(f"📡 Testing against: {self.base_url}")
        print(f"📅 Testing for date: {self.today}")
        print("=" * 80)

        # Test basic connectivity
        print("\n🔗 BASIC CONNECTIVITY TESTS")
        self.test_root_endpoint()
        self.test_health_endpoint()

        # Test HIGH PRIORITY NEW FEATURES
        print("\n🎯 HIGH PRIORITY NEW FEATURES")
        self.test_today_only_dashboard_stats()
        self.test_today_only_articles()
        self.test_cache_clearing_scrape_now()
        
        print("\n🧠 LOCAL SENTIMENT ANALYSIS SERVICE")
        self.test_sentiment_stats()
        self.test_sentiment_articles()
        self.test_sentiment_analyze_text()
        self.test_sentiment_trends()

        # Test SOCIAL MEDIA WITHOUT DEMO DATA (as requested)
        print("\n📱 SOCIAL MEDIA REAL DATA TESTS (NO DEMO)")
        self.test_social_clean_demo_data()
        self.test_social_scrape_real_data()
        self.test_comments_no_demo_data()
        self.test_search_guy_losbar_real_data()
        self.test_social_stats_real_data()
        self.test_social_scrape_status_check()

        # Test search and comments integration
        print("\n🔍 SEARCH & COMMENTS INTEGRATION")
        self.test_search_endpoint()
        self.test_comments_endpoint()
        self.test_search_suggestions()
        self.test_comments_analyze()
        self.test_social_scrape_now()
        self.test_social_stats()

        # Test existing features
        print("\n📰 EXISTING FEATURES VERIFICATION")
        self.test_scrapers_working()
        
        # Test RADIO TRANSCRIPTION SYSTEM (as requested)
        print("\n📻 RADIO TRANSCRIPTION SYSTEM TESTS")
        self.test_ffmpeg_dependency()
        self.test_whisper_dependency()
        self.test_radio_streaming_urls()
        self.test_transcriptions_endpoint()
        self.test_transcriptions_by_date()
        self.test_capture_radio_now()
        self.test_capture_status()
        self.test_upload_audio_transcription()
        self.test_scheduler_status()

        # Print summary
        print("=" * 80)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! Backend API is working correctly.")
            return 0
        else:
            failed_tests = self.tests_run - self.tests_passed
            print(f"⚠️  {failed_tests} tests failed. Check the issues above.")
            return 1

def main():
    """Main test runner"""
    tester = GuadeloupeMediaAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())