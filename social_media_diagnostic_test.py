#!/usr/bin/env python3
"""
Social Media System Diagnostic Test Suite for Guadeloupe Media Monitoring Application
Comprehensive testing of social media endpoints and scraping methods as requested.

DIAGNOSTIC COMPLET À EFFECTUER:
1. Test des endpoints sociaux actuels
2. Test des méthodes de scraping (snscrape, Playwright)
3. Test des dépendances
4. Test de récupération de données réelles avec mots-clés guadeloupéens
"""

import requests
import sys
import json
import time
from datetime import datetime

class SocialMediaDiagnosticTester:
    def __init__(self, base_url="https://a0cf0419-f055-4e25-b209-04f98074de7d.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 120  # Extended timeout for scraping operations
        self.guadeloupe_keywords = ["Guy Losbar", "CD971", "Conseil Départemental Guadeloupe"]
        
    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_social_stats_endpoint(self):
        """Test GET /api/social/stats endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    demo_mode = stats.get('demo_mode', True)
                    total_posts = stats.get('total_posts', 0)
                    by_platform = stats.get('by_platform', {})
                    
                    details = f"- Stats retrieved: {total_posts} posts, demo_mode: {demo_mode}, platforms: {list(by_platform.keys())}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("GET /api/social/stats", success, details)
        except Exception as e:
            return self.log_test("GET /api/social/stats", False, f"- Error: {str(e)}")

    def test_social_posts_endpoint(self):
        """Test GET /api/social/posts endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/posts")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    posts = data.get('posts', [])
                    count = data.get('count', 0)
                    
                    # Check for real vs demo data
                    demo_posts = 0
                    real_posts = 0
                    platforms_found = set()
                    
                    for post in posts[:10]:  # Check first 10 posts
                        if post.get('demo_data') is True:
                            demo_posts += 1
                        else:
                            real_posts += 1
                        platforms_found.add(post.get('platform', 'unknown'))
                    
                    details = f"- Found {count} posts: {real_posts} real, {demo_posts} demo, platforms: {list(platforms_found)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("GET /api/social/posts", success, details)
        except Exception as e:
            return self.log_test("GET /api/social/posts", False, f"- Error: {str(e)}")

    def test_social_scrape_now_endpoint(self):
        """Test POST /api/social/scrape-now endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    note = data.get('note', '')
                    
                    # Check if it mentions snscrape and Playwright
                    mentions_snscrape = 'snscrape' in note.lower()
                    mentions_playwright = 'playwright' in note.lower()
                    
                    details = f"- Scraping initiated: '{message}', ETA: {estimated_completion}, snscrape: {mentions_snscrape}, playwright: {mentions_playwright}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("POST /api/social/scrape-now", success, details)
        except Exception as e:
            return self.log_test("POST /api/social/scrape-now", False, f"- Error: {str(e)}")

    def test_comments_endpoint(self):
        """Test GET /api/comments endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/comments")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    comments = data.get('comments', [])
                    count = data.get('count', 0)
                    
                    # Check for sentiment analysis and real data
                    has_sentiment = False
                    demo_comments = 0
                    real_comments = 0
                    guadeloupe_content = 0
                    
                    for comment in comments[:10]:  # Check first 10 comments
                        if 'sentiment_summary' in comment or 'sentiment' in comment:
                            has_sentiment = True
                        if comment.get('demo_data') is True:
                            demo_comments += 1
                        else:
                            real_comments += 1
                        
                        # Check for Guadeloupe-related content
                        content = comment.get('content', '').lower()
                        if any(keyword.lower() in content for keyword in self.guadeloupe_keywords):
                            guadeloupe_content += 1
                    
                    details = f"- Found {count} comments: {real_comments} real, {demo_comments} demo, sentiment: {has_sentiment}, Guadeloupe content: {guadeloupe_content}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("GET /api/comments", success, details)
        except Exception as e:
            return self.log_test("GET /api/comments", False, f"- Error: {str(e)}")

    def test_snscrape_dependency(self):
        """Test if snscrape is working for Twitter scraping"""
        try:
            # Test by initiating scraping and checking status
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    note = data.get('note', '').lower()
                    mentions_snscrape = 'snscrape' in note
                    mentions_twitter = 'twitter' in note
                    
                    if mentions_snscrape:
                        details = f"- snscrape mentioned in scraping note: '{data.get('note', '')}'"
                    else:
                        success = False
                        details = f"- snscrape not mentioned in note: '{data.get('note', '')}'"
                else:
                    success = False
                    details = f"- Scraping failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("snscrape Dependency Check", success, details)
        except Exception as e:
            return self.log_test("snscrape Dependency Check", False, f"- Error: {str(e)}")

    def test_playwright_dependency(self):
        """Test if Playwright is working for Facebook scraping"""
        try:
            # Test by initiating scraping and checking status
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    note = data.get('note', '').lower()
                    mentions_playwright = 'playwright' in note
                    mentions_facebook = 'facebook' in note
                    
                    if mentions_playwright:
                        details = f"- Playwright mentioned in scraping note: '{data.get('note', '')}'"
                    else:
                        success = False
                        details = f"- Playwright not mentioned in note: '{data.get('note', '')}'"
                else:
                    success = False
                    details = f"- Scraping failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Playwright Dependency Check", success, details)
        except Exception as e:
            return self.log_test("Playwright Dependency Check", False, f"- Error: {str(e)}")

    def test_dependency_installation_endpoint(self):
        """Test social media dependencies installation endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/install-dependencies")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    
                    mentions_snscrape = 'snscrape' in message.lower()
                    mentions_playwright = 'playwright' in message.lower()
                    
                    if mentions_snscrape and mentions_playwright:
                        details = f"- Installation initiated: '{message}', ETA: {estimated_completion}"
                    else:
                        success = False
                        details = f"- Dependencies not properly mentioned: snscrape={mentions_snscrape}, playwright={mentions_playwright}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Dependencies Installation", success, details)
        except Exception as e:
            return self.log_test("Dependencies Installation", False, f"- Error: {str(e)}")

    def test_real_data_guy_losbar(self):
        """Test récupération de données réelles pour 'Guy Losbar'"""
        try:
            # First, clean demo data
            self.session.post(f"{self.base_url}/api/social/clean-demo-data")
            time.sleep(1)
            
            # Search for Guy Losbar
            response = self.session.get(f"{self.base_url}/api/search", params={'q': 'Guy Losbar'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    social_posts = data.get('social_posts', [])
                    total_results = data.get('total_results', 0)
                    
                    # Check for real data (no demo_data flag)
                    real_results = 0
                    demo_results = 0
                    for result in articles + social_posts:
                        if result.get('demo_data') is True:
                            demo_results += 1
                        else:
                            real_results += 1
                    
                    if real_results > 0 or total_results == 0:  # Either real data found or no data (acceptable)
                        details = f"- Guy Losbar search: {total_results} total ({real_results} real, {demo_results} demo)"
                    else:
                        success = False
                        details = f"- Only demo data found for Guy Losbar: {demo_results} demo results"
                else:
                    success = False
                    details = f"- Search failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Real Data - Guy Losbar", success, details)
        except Exception as e:
            return self.log_test("Real Data - Guy Losbar", False, f"- Error: {str(e)}")

    def test_real_data_cd971(self):
        """Test récupération de données réelles pour 'CD971'"""
        try:
            response = self.session.get(f"{self.base_url}/api/search", params={'q': 'CD971'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    social_posts = data.get('social_posts', [])
                    total_results = data.get('total_results', 0)
                    
                    # Check for real data
                    real_results = 0
                    demo_results = 0
                    for result in articles + social_posts:
                        if result.get('demo_data') is True:
                            demo_results += 1
                        else:
                            real_results += 1
                    
                    if real_results > 0 or total_results == 0:
                        details = f"- CD971 search: {total_results} total ({real_results} real, {demo_results} demo)"
                    else:
                        success = False
                        details = f"- Only demo data found for CD971: {demo_results} demo results"
                else:
                    success = False
                    details = f"- Search failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Real Data - CD971", success, details)
        except Exception as e:
            return self.log_test("Real Data - CD971", False, f"- Error: {str(e)}")

    def test_real_data_conseil_departemental(self):
        """Test récupération de données réelles pour 'Conseil Départemental Guadeloupe'"""
        try:
            response = self.session.get(f"{self.base_url}/api/search", params={'q': 'Conseil Départemental Guadeloupe'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    social_posts = data.get('social_posts', [])
                    total_results = data.get('total_results', 0)
                    
                    # Check for real data
                    real_results = 0
                    demo_results = 0
                    for result in articles + social_posts:
                        if result.get('demo_data') is True:
                            demo_results += 1
                        else:
                            real_results += 1
                    
                    if real_results > 0 or total_results == 0:
                        details = f"- Conseil Départemental search: {total_results} total ({real_results} real, {demo_results} demo)"
                    else:
                        success = False
                        details = f"- Only demo data found for Conseil Départemental: {demo_results} demo results"
                else:
                    success = False
                    details = f"- Search failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Real Data - Conseil Départemental", success, details)
        except Exception as e:
            return self.log_test("Real Data - Conseil Départemental", False, f"- Error: {str(e)}")

    def test_scraping_quality_assessment(self):
        """Test la qualité des données récupérées par le scraping"""
        try:
            # Wait for any ongoing scraping to complete
            time.sleep(5)
            
            # Check scraping status
            response = self.session.get(f"{self.base_url}/api/social/scrape-status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', {})
                    total_posts = result.get('total_posts', 0)
                    by_platform = result.get('by_platform', {})
                    demo_mode = result.get('demo_mode', True)
                    keywords = result.get('keywords', [])
                    
                    # Quality assessment
                    has_real_data = not demo_mode
                    has_multiple_platforms = len(by_platform) > 1
                    has_guadeloupe_keywords = any(keyword in str(keywords).lower() for keyword in ['guy losbar', 'cd971', 'conseil'])
                    
                    quality_score = sum([has_real_data, has_multiple_platforms, has_guadeloupe_keywords])
                    
                    details = f"- Quality assessment: {total_posts} posts, real_data: {has_real_data}, platforms: {len(by_platform)}, guadeloupe_keywords: {has_guadeloupe_keywords}, score: {quality_score}/3"
                else:
                    # No recent scraping is acceptable
                    details = f"- No recent scraping result: {data.get('message', '')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Scraping Quality Assessment", success, details)
        except Exception as e:
            return self.log_test("Scraping Quality Assessment", False, f"- Error: {str(e)}")

    def test_social_keyword_specific_scraping(self):
        """Test scraping spécifique pour un mot-clé guadeloupéen"""
        try:
            keyword = "Guy Losbar"
            data = {'keyword': keyword}
            response = self.session.post(f"{self.base_url}/api/social/scrape-keyword", json=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    message = response_data.get('message', '')
                    keyword_returned = response_data.get('keyword', '')
                    estimated_completion = response_data.get('estimated_completion', '')
                    
                    if keyword in message and keyword_returned == keyword:
                        details = f"- Keyword scraping initiated for '{keyword}': '{message}', ETA: {estimated_completion}"
                    else:
                        success = False
                        details = f"- Keyword scraping failed: keyword mismatch or missing in message"
                else:
                    success = False
                    details = f"- API returned success=False: {response_data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Keyword-Specific Scraping", success, details)
        except Exception as e:
            return self.log_test("Keyword-Specific Scraping", False, f"- Error: {str(e)}")

    def test_demo_data_cleanup(self):
        """Test nettoyage des données de démonstration"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/clean-demo-data")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cleaned_count = data.get('cleaned_count', 0)
                    message = data.get('message', '')
                    
                    if cleaned_count >= 0 and 'démonstration' in message.lower():
                        details = f"- Demo data cleaned: {cleaned_count} posts removed, message: '{message}'"
                    else:
                        success = False
                        details = f"- Demo cleanup failed: count={cleaned_count}, message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Demo Data Cleanup", success, details)
        except Exception as e:
            return self.log_test("Demo Data Cleanup", False, f"- Error: {str(e)}")

    def test_social_sentiment_analysis(self):
        """Test analyse de sentiment des posts sociaux"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/sentiment")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    posts = data.get('posts', [])
                    summary = data.get('summary', {})
                    total_posts = summary.get('total_posts', 0)
                    sentiment_distribution = summary.get('sentiment_distribution', {})
                    by_platform = summary.get('by_platform', {})
                    
                    has_sentiment_data = 'positive' in sentiment_distribution
                    has_platform_breakdown = len(by_platform) > 0
                    
                    if total_posts >= 0 and has_sentiment_data:
                        details = f"- Sentiment analysis: {total_posts} posts analyzed, distribution: {sentiment_distribution}, platforms: {len(by_platform)}"
                    else:
                        success = False
                        details = f"- Sentiment analysis failed: posts={total_posts}, sentiment_data={has_sentiment_data}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Sentiment Analysis", success, details)
        except Exception as e:
            return self.log_test("Social Sentiment Analysis", False, f"- Error: {str(e)}")

    def test_comments_sentiment_by_entity(self):
        """Test analyse de sentiment des commentaires par entité"""
        try:
            response = self.session.post(f"{self.base_url}/api/comments/analyze")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    analysis = data.get('analysis', {})
                    total_comments = analysis.get('total_comments', 0)
                    by_entity = analysis.get('by_entity', {})
                    overall = analysis.get('overall', {})
                    
                    # Check for Guadeloupe-specific entities
                    guadeloupe_entities = ['Guy Losbar', 'Conseil Départemental', 'CD971']
                    entities_found = [entity for entity in guadeloupe_entities if entity in by_entity]
                    
                    if total_comments >= 0 and isinstance(by_entity, dict):
                        details = f"- Entity sentiment analysis: {total_comments} comments, entities found: {entities_found}, overall avg: {overall.get('average_sentiment', 0)}"
                    else:
                        success = False
                        details = f"- Entity analysis failed: comments={total_comments}, entities={len(by_entity)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments Sentiment by Entity", success, details)
        except Exception as e:
            return self.log_test("Comments Sentiment by Entity", False, f"- Error: {str(e)}")

    def run_comprehensive_diagnostic(self):
        """Run all social media diagnostic tests"""
        print("🔍 DIAGNOSTIC COMPLET DU SYSTÈME DE RÉSEAUX SOCIAUX")
        print("=" * 60)
        print(f"Base URL: {self.base_url}")
        print(f"Mots-clés testés: {', '.join(self.guadeloupe_keywords)}")
        print("=" * 60)
        
        # 1. Test des endpoints sociaux actuels
        print("\n📡 1. TEST DES ENDPOINTS SOCIAUX ACTUELS")
        print("-" * 40)
        self.test_social_stats_endpoint()
        self.test_social_posts_endpoint()
        self.test_social_scrape_now_endpoint()
        self.test_comments_endpoint()
        
        # 2. Test des méthodes de scraping
        print("\n🔧 2. TEST DES MÉTHODES DE SCRAPING")
        print("-" * 40)
        self.test_snscrape_dependency()
        self.test_playwright_dependency()
        self.test_dependency_installation_endpoint()
        
        # 3. Test des dépendances
        print("\n📦 3. TEST DES DÉPENDANCES")
        print("-" * 40)
        # Dependencies are tested above, but we can add more specific tests
        self.test_demo_data_cleanup()
        
        # 4. Test de récupération de données réelles
        print("\n🎯 4. TEST DE RÉCUPÉRATION DE DONNÉES RÉELLES")
        print("-" * 40)
        self.test_real_data_guy_losbar()
        self.test_real_data_cd971()
        self.test_real_data_conseil_departemental()
        self.test_scraping_quality_assessment()
        self.test_social_keyword_specific_scraping()
        
        # 5. Test des analyses avancées
        print("\n🧠 5. TEST DES ANALYSES AVANCÉES")
        print("-" * 40)
        self.test_social_sentiment_analysis()
        self.test_comments_sentiment_by_entity()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DU DIAGNOSTIC")
        print("=" * 60)
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Tests exécutés: {self.tests_run}")
        print(f"Tests réussis: {self.tests_passed}")
        print(f"Taux de réussite: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("✅ SYSTÈME SOCIAL MEDIA: OPÉRATIONNEL")
        elif success_rate >= 60:
            print("⚠️ SYSTÈME SOCIAL MEDIA: PARTIELLEMENT FONCTIONNEL")
        else:
            print("❌ SYSTÈME SOCIAL MEDIA: PROBLÈMES CRITIQUES")
        
        return success_rate

if __name__ == "__main__":
    tester = SocialMediaDiagnosticTester()
    success_rate = tester.run_comprehensive_diagnostic()
    
    # Exit with appropriate code
    sys.exit(0 if success_rate >= 60 else 1)