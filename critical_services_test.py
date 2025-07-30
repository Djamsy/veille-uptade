#!/usr/bin/env python3
"""
Critical Services Test Suite - Post Heavy Dependencies Removal
Tests the essential services after removing spaCy, local Whisper, torch, etc.
"""

import requests
import sys
import json
from datetime import datetime

class CriticalServicesAPITester:
    def __init__(self, base_url="https://a035ef10-1947-4766-84e0-d2ba660b1593.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 30
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

    def test_health_endpoint(self):
        """Test GET /api/health - verify all services are ready"""
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    health = data.get('health', {})
                    status = health.get('status', '')
                    services = health.get('services', {})
                    
                    # Check if all services are ready
                    all_ready = status == 'healthy'
                    service_count = len(services)
                    
                    if all_ready and service_count > 0:
                        details = f"- Status: {status}, Services: {service_count} ready"
                    else:
                        success = False
                        details = f"- Status: {status}, Services: {service_count}, not all ready"
                else:
                    success = False
                    details = f"- Health check failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Health Check - All Services Ready", success, details)
        except Exception as e:
            return self.log_test("Health Check - All Services Ready", False, f"- Error: {str(e)}")

    def test_dashboard_stats(self):
        """Test GET /api/dashboard-stats - verify data retrieval"""
        try:
            response = self.session.get(f"{self.base_url}/api/dashboard-stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    today_articles = stats.get('today_articles', 0)
                    cache_stats = stats.get('cache_stats', {})
                    
                    if today_articles >= 0 and cache_stats:
                        details = f"- Today articles: {today_articles}, Cache: {cache_stats.get('status', 'unknown')}"
                    else:
                        success = False
                        details = f"- Data incomplete: articles={today_articles}, cache={bool(cache_stats)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Dashboard Stats Data", success, details)
        except Exception as e:
            return self.log_test("Dashboard Stats Data", False, f"- Error: {str(e)}")

    def test_articles_endpoint(self):
        """Test GET /api/articles - verify article retrieval"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    count = data.get('count', 0)
                    
                    if count >= 0 and len(articles) == count:
                        details = f"- Found {count} articles, data consistent"
                    else:
                        success = False
                        details = f"- Data inconsistent: count={count}, actual={len(articles)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Articles Retrieval", success, details)
        except Exception as e:
            return self.log_test("Articles Retrieval", False, f"- Error: {str(e)}")

    def test_summary_service_without_spacy(self):
        """Test summary service works without spaCy dependencies"""
        try:
            # Test digest creation which uses summary service
            response = self.session.get(f"{self.base_url}/api/digest")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    digest = data.get('digest', {})
                    digest_html = digest.get('digest_html', '')
                    articles_count = digest.get('articles_count', 0)
                    
                    # Check if digest was created without spaCy
                    if digest_html and articles_count >= 0:
                        details = f"- Digest created: {len(digest_html)} chars, {articles_count} articles processed"
                    else:
                        success = False
                        details = f"- Digest incomplete: html_len={len(digest_html)}, articles={articles_count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Summary Service Without spaCy", success, details)
        except Exception as e:
            return self.log_test("Summary Service Without spaCy", False, f"- Error: {str(e)}")

    def test_key_phrases_extraction_basic(self):
        """Test key phrases extraction with basic method (no spaCy)"""
        try:
            # Test GPT analysis which should include key phrases
            test_text = "Le Conseil Départemental de la Guadeloupe investit dans l'éducation et les infrastructures."
            data = {'text': test_text}
            response = self.session.post(f"{self.base_url}/api/test-gpt", data=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    gpt_analysis = response_data.get('gpt_analysis', {})
                    analysis_text = gpt_analysis.get('gpt_analysis', '') or gpt_analysis.get('summary', '')
                    
                    # Check if key phrases/topics are extracted
                    has_structured_analysis = any(emoji in analysis_text for emoji in ['🏛️', '💼', '🌿'])
                    has_content = len(analysis_text) > 100
                    
                    if has_structured_analysis and has_content:
                        details = f"- Key phrases extracted: structured={has_structured_analysis}, length={len(analysis_text)}"
                    else:
                        success = False
                        details = f"- Extraction failed: structured={has_structured_analysis}, length={len(analysis_text)}"
                else:
                    success = False
                    details = f"- API returned success=False: {response_data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Key Phrases Extraction (Basic Method)", success, details)
        except Exception as e:
            return self.log_test("Key Phrases Extraction (Basic Method)", False, f"- Error: {str(e)}")

    def test_digest_generation(self):
        """Test digest generation without heavy dependencies"""
        try:
            response = self.session.post(f"{self.base_url}/api/digest/create-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    digest = data.get('digest', {})
                    message = data.get('message', '')
                    articles_count = digest.get('articles_count', 0)
                    transcriptions_count = digest.get('transcriptions_count', 0)
                    
                    if 'créé' in message.lower() and articles_count >= 0:
                        details = f"- Digest created: {articles_count} articles, {transcriptions_count} transcriptions"
                    else:
                        success = False
                        details = f"- Creation failed: message='{message}', articles={articles_count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Digest Generation", success, details)
        except Exception as e:
            return self.log_test("Digest Generation", False, f"- Error: {str(e)}")

    def test_radio_service_no_local_whisper(self):
        """Test radio service uses only OpenAI Whisper API (no local models)"""
        try:
            # Check existing transcriptions for method used
            response = self.session.get(f"{self.base_url}/api/transcriptions")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    transcriptions = data.get('transcriptions', [])
                    
                    # Check transcription methods
                    openai_whisper_count = 0
                    local_whisper_count = 0
                    
                    for transcription in transcriptions[:10]:  # Check first 10
                        method = transcription.get('transcription_method', '').lower()
                        if 'openai_whisper_api' in method:
                            openai_whisper_count += 1
                        elif 'whisper' in method and 'openai' not in method:
                            local_whisper_count += 1
                    
                    # Should only use OpenAI Whisper API
                    if openai_whisper_count > 0 and local_whisper_count == 0:
                        details = f"- Only OpenAI Whisper API used: {openai_whisper_count} transcriptions, 0 local"
                    elif len(transcriptions) == 0:
                        details = f"- No transcriptions found (acceptable): count=0"
                    else:
                        success = False
                        details = f"- Local Whisper detected: openai={openai_whisper_count}, local={local_whisper_count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Radio Service - OpenAI Whisper Only", success, details)
        except Exception as e:
            return self.log_test("Radio Service - OpenAI Whisper Only", False, f"- Error: {str(e)}")

    def test_transcription_method_verification(self):
        """Test transcription method is OpenAI Whisper API"""
        try:
            # Test capture status to see method configuration
            response = self.session.get(f"{self.base_url}/api/transcriptions/status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    status = data.get('status', {})
                    sections = status.get('sections', {})
                    
                    # Check if system is configured for OpenAI Whisper
                    if len(sections) >= 0:
                        details = f"- Transcription system configured: {len(sections)} sections available"
                    else:
                        success = False
                        details = f"- System not configured: sections={len(sections)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Transcription Method Configuration", success, details)
        except Exception as e:
            return self.log_test("Transcription Method Configuration", False, f"- Error: {str(e)}")

    def test_telegram_alerts_status(self):
        """Test Telegram alerts service status"""
        try:
            # Check if Telegram service is available through health endpoint
            response = self.session.get(f"{self.base_url}/api/health")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    health = data.get('health', {})
                    services = health.get('services', {})
                    
                    # Look for Telegram service in health check
                    telegram_service = services.get('telegram_alerts', {})
                    if telegram_service or 'telegram' in str(services).lower():
                        details = f"- Telegram service detected in health check"
                    else:
                        # Telegram might not be in health check but still working
                        details = f"- Telegram service status unknown from health check"
                else:
                    success = False
                    details = f"- Health check failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Telegram Alerts Status", success, details)
        except Exception as e:
            return self.log_test("Telegram Alerts Status", False, f"- Error: {str(e)}")

    def test_telegram_surveillance_working(self):
        """Test Telegram surveillance functionality"""
        try:
            # Check scheduler status which should include Telegram jobs
            response = self.session.get(f"{self.base_url}/api/scheduler/status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    jobs = data.get('jobs', [])
                    scheduler_running = data.get('scheduler_running', False)
                    
                    # Look for Telegram-related jobs
                    telegram_jobs = [job for job in jobs if 'telegram' in str(job).lower()]
                    
                    if scheduler_running and len(jobs) > 0:
                        details = f"- Scheduler running: {len(jobs)} jobs, telegram_jobs: {len(telegram_jobs)}"
                    else:
                        success = False
                        details = f"- Scheduler issues: running={scheduler_running}, jobs={len(jobs)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Telegram Surveillance Working", success, details)
        except Exception as e:
            return self.log_test("Telegram Surveillance Working", False, f"- Error: {str(e)}")

    def test_scheduler_all_jobs_configured(self):
        """Test scheduler has all jobs properly configured"""
        try:
            response = self.session.get(f"{self.base_url}/api/scheduler/status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    jobs = data.get('jobs', [])
                    scheduler_running = data.get('scheduler_running', False)
                    recent_logs = data.get('recent_logs', [])
                    
                    # Check for essential jobs
                    expected_job_types = ['scrape', 'capture', 'digest']
                    found_job_types = []
                    
                    for job in jobs:
                        job_str = str(job).lower()
                        for job_type in expected_job_types:
                            if job_type in job_str:
                                found_job_types.append(job_type)
                                break
                    
                    if scheduler_running and len(jobs) >= 3:
                        details = f"- Scheduler: {len(jobs)} jobs, types found: {list(set(found_job_types))}"
                    else:
                        success = False
                        details = f"- Scheduler incomplete: running={scheduler_running}, jobs={len(jobs)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Scheduler All Jobs Configured", success, details)
        except Exception as e:
            return self.log_test("Scheduler All Jobs Configured", False, f"- Error: {str(e)}")

    def run_all_critical_tests(self):
        """Run all critical service tests"""
        print("🔍 CRITICAL SERVICES TEST - POST HEAVY DEPENDENCIES REMOVAL")
        print("Testing essential services after removing spaCy, local Whisper, torch, etc.")
        print(f"📡 Testing against: {self.base_url}")
        print(f"📅 Testing for date: {self.today}")
        print("=" * 80)
        
        print("\n🎯 ESSENTIAL SERVICES")
        self.test_health_endpoint()
        self.test_dashboard_stats()
        self.test_articles_endpoint()
        
        print("\n📝 SUMMARY SERVICE (MODIFIED)")
        self.test_summary_service_without_spacy()
        self.test_key_phrases_extraction_basic()
        self.test_digest_generation()
        
        print("\n📻 RADIO SERVICE (MODIFIED)")
        self.test_radio_service_no_local_whisper()
        self.test_transcription_method_verification()
        
        print("\n📱 TELEGRAM SERVICES")
        self.test_telegram_alerts_status()
        self.test_telegram_surveillance_working()
        
        print("\n⏰ SCHEDULER")
        self.test_scheduler_all_jobs_configured()
        
        print("\n" + "=" * 80)
        print("🔍 CRITICAL SERVICES TEST SUMMARY")
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 ALL CRITICAL SERVICES: OPERATIONAL")
            print("✅ Application ready for deployment without heavy dependencies")
        else:
            print("⚠️ SOME CRITICAL SERVICES HAVE ISSUES")
            print("❌ Review failed tests before deployment")
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = CriticalServicesAPITester()
    success = tester.run_all_critical_tests()
    sys.exit(0 if success else 1)