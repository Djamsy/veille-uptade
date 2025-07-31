#!/usr/bin/env python3
"""
Scrapers Test Suite - Testing scrapers that need retesting
Tests France-Antilles, RCI, La 1ère, KaribInfo, and caching system
"""

import requests
import sys
import json
import time
from datetime import datetime

class ScrapersAPITester:
    def __init__(self, base_url="https://bb8f662d-6347-4222-9f33-1c130098c9a0.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 60  # Longer timeout for scraping operations
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

    def test_france_antilles_scraper(self):
        """Test France-Antilles scraper functionality"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Look for France-Antilles articles
                    france_antilles_articles = [
                        article for article in articles 
                        if 'france-antilles' in article.get('source', '').lower()
                    ]
                    
                    if len(france_antilles_articles) > 0:
                        # Check article structure
                        sample_article = france_antilles_articles[0]
                        has_title = bool(sample_article.get('title'))
                        has_url = bool(sample_article.get('url'))
                        has_date = bool(sample_article.get('date'))
                        
                        if has_title and has_url and has_date:
                            details = f"- Found {len(france_antilles_articles)} articles with proper structure"
                        else:
                            success = False
                            details = f"- Articles missing fields: title={has_title}, url={has_url}, date={has_date}"
                    else:
                        success = False
                        details = f"- No France-Antilles articles found in {len(articles)} total articles"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("France-Antilles Scraper", success, details)
        except Exception as e:
            return self.log_test("France-Antilles Scraper", False, f"- Error: {str(e)}")

    def test_rci_guadeloupe_scraper(self):
        """Test RCI Guadeloupe scraper functionality"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Look for RCI articles
                    rci_articles = [
                        article for article in articles 
                        if 'rci' in article.get('source', '').lower()
                    ]
                    
                    if len(rci_articles) > 0:
                        # Check article structure
                        sample_article = rci_articles[0]
                        has_title = bool(sample_article.get('title'))
                        has_url = bool(sample_article.get('url'))
                        has_date = bool(sample_article.get('date'))
                        
                        if has_title and has_url and has_date:
                            details = f"- Found {len(rci_articles)} articles with proper structure"
                        else:
                            success = False
                            details = f"- Articles missing fields: title={has_title}, url={has_url}, date={has_date}"
                    else:
                        success = False
                        details = f"- No RCI articles found in {len(articles)} total articles"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("RCI Guadeloupe Scraper", success, details)
        except Exception as e:
            return self.log_test("RCI Guadeloupe Scraper", False, f"- Error: {str(e)}")

    def test_la_1ere_guadeloupe_scraper(self):
        """Test La 1ère Guadeloupe scraper functionality"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Look for La 1ère articles
                    la_1ere_articles = [
                        article for article in articles 
                        if 'la 1ère' in article.get('source', '').lower() or 'guadeloupe première' in article.get('source', '').lower()
                    ]
                    
                    if len(la_1ere_articles) > 0:
                        # Check article structure
                        sample_article = la_1ere_articles[0]
                        has_title = bool(sample_article.get('title'))
                        has_url = bool(sample_article.get('url'))
                        has_date = bool(sample_article.get('date'))
                        
                        if has_title and has_url and has_date:
                            details = f"- Found {len(la_1ere_articles)} articles with proper structure"
                        else:
                            success = False
                            details = f"- Articles missing fields: title={has_title}, url={has_url}, date={has_date}"
                    else:
                        success = False
                        details = f"- No La 1ère articles found in {len(articles)} total articles"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("La 1ère Guadeloupe Scraper", success, details)
        except Exception as e:
            return self.log_test("La 1ère Guadeloupe Scraper", False, f"- Error: {str(e)}")

    def test_karibinfo_scraper(self):
        """Test KaribInfo scraper functionality"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Look for KaribInfo articles
                    karibinfo_articles = [
                        article for article in articles 
                        if 'karibinfo' in article.get('source', '').lower()
                    ]
                    
                    if len(karibinfo_articles) > 0:
                        # Check article structure
                        sample_article = karibinfo_articles[0]
                        has_title = bool(sample_article.get('title'))
                        has_url = bool(sample_article.get('url'))
                        has_date = bool(sample_article.get('date'))
                        
                        if has_title and has_url and has_date:
                            details = f"- Found {len(karibinfo_articles)} articles with proper structure"
                        else:
                            success = False
                            details = f"- Articles missing fields: title={has_title}, url={has_url}, date={has_date}"
                    else:
                        success = False
                        details = f"- No KaribInfo articles found in {len(articles)} total articles"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("KaribInfo Scraper", success, details)
        except Exception as e:
            return self.log_test("KaribInfo Scraper", False, f"- Error: {str(e)}")

    def test_all_scrapers_working(self):
        """Test that all 4 scrapers are working together"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Count articles by source
                    sources_count = {}
                    for article in articles:
                        source = article.get('source', '').lower()
                        if 'france-antilles' in source:
                            sources_count['France-Antilles'] = sources_count.get('France-Antilles', 0) + 1
                        elif 'rci' in source:
                            sources_count['RCI'] = sources_count.get('RCI', 0) + 1
                        elif 'la 1ère' in source or 'guadeloupe première' in source:
                            sources_count['La 1ère'] = sources_count.get('La 1ère', 0) + 1
                        elif 'karibinfo' in source:
                            sources_count['KaribInfo'] = sources_count.get('KaribInfo', 0) + 1
                    
                    working_scrapers = len(sources_count)
                    total_articles = sum(sources_count.values())
                    
                    if working_scrapers >= 3:  # At least 3 out of 4 scrapers working
                        details = f"- {working_scrapers}/4 scrapers working: {sources_count}, total: {total_articles}"
                    else:
                        success = False
                        details = f"- Only {working_scrapers}/4 scrapers working: {sources_count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("All Scrapers Working Together", success, details)
        except Exception as e:
            return self.log_test("All Scrapers Working Together", False, f"- Error: {str(e)}")

    def test_intelligent_caching_system(self):
        """Test intelligent caching system functionality"""
        try:
            response = self.session.get(f"{self.base_url}/api/cache/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cache_stats = data.get('cache_stats', {})
                    
                    # Check cache system status
                    if isinstance(cache_stats, dict) and len(cache_stats) > 0:
                        cache_status = cache_stats.get('status', 'unknown')
                        cache_entries = cache_stats.get('total_entries', 0)
                        
                        if cache_status in ['active', 'enabled', 'healthy']:
                            details = f"- Cache active: status={cache_status}, entries={cache_entries}"
                        else:
                            success = False
                            details = f"- Cache not active: status={cache_status}, entries={cache_entries}"
                    else:
                        success = False
                        details = f"- Cache stats incomplete: {cache_stats}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Intelligent Caching System", success, details)
        except Exception as e:
            return self.log_test("Intelligent Caching System", False, f"- Error: {str(e)}")

    def test_cache_invalidation(self):
        """Test cache invalidation functionality"""
        try:
            # Test cache invalidation
            response = self.session.post(f"{self.base_url}/api/cache/invalidate", json={'pattern': 'test'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    
                    if 'invalidé' in message.lower() or 'invalidated' in message.lower():
                        details = f"- Cache invalidation working: '{message}'"
                    else:
                        success = False
                        details = f"- Invalidation message unclear: '{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Cache Invalidation", success, details)
        except Exception as e:
            return self.log_test("Cache Invalidation", False, f"- Error: {str(e)}")

    def test_cache_warming(self):
        """Test cache warming functionality"""
        try:
            response = self.session.post(f"{self.base_url}/api/cache/warm")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    
                    if 'préchauffé' in message.lower() or 'warmed' in message.lower():
                        details = f"- Cache warming working: '{message}'"
                    else:
                        success = False
                        details = f"- Warming message unclear: '{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Cache Warming", success, details)
        except Exception as e:
            return self.log_test("Cache Warming", False, f"- Error: {str(e)}")

    def test_scrape_now_with_cache_clearing(self):
        """Test scrape-now endpoint with cache clearing"""
        try:
            response = self.session.post(f"{self.base_url}/api/articles/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cache_cleared = data.get('cache_cleared', False)
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    
                    if cache_cleared and 'cache' in message.lower() and estimated_completion:
                        details = f"- Scraping initiated with cache clearing: '{message}', ETA: {estimated_completion}"
                    else:
                        success = False
                        details = f"- Cache clearing not confirmed: cleared={cache_cleared}, message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Scrape Now with Cache Clearing", success, details)
        except Exception as e:
            return self.log_test("Scrape Now with Cache Clearing", False, f"- Error: {str(e)}")

    def test_scrape_status(self):
        """Test scrape status endpoint"""
        try:
            # Wait a moment for scraping to potentially start
            time.sleep(2)
            
            response = self.session.get(f"{self.base_url}/api/articles/scrape-status")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    result = data.get('result', {})
                    
                    if isinstance(result, dict) and len(result) > 0:
                        scraped_at = result.get('scraped_at', '')
                        total_articles = result.get('total_articles', 0)
                        details = f"- Scrape status available: scraped_at='{scraped_at}', articles={total_articles}"
                    else:
                        success = False
                        details = f"- Scrape status incomplete: {result}"
                else:
                    # No recent scraping is also acceptable
                    message = data.get('message', '')
                    details = f"- No recent scraping (acceptable): '{message}'"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Scrape Status", success, details)
        except Exception as e:
            return self.log_test("Scrape Status", False, f"- Error: {str(e)}")

    def run_all_scraper_tests(self):
        """Run all scraper tests"""
        print("🔍 SCRAPERS TEST SUITE - RETESTING REQUIRED SCRAPERS")
        print("Testing France-Antilles, RCI, La 1ère, KaribInfo, and caching system")
        print(f"📡 Testing against: {self.base_url}")
        print(f"📅 Testing for date: {self.today}")
        print("=" * 80)
        
        print("\n📰 INDIVIDUAL SCRAPERS")
        self.test_france_antilles_scraper()
        self.test_rci_guadeloupe_scraper()
        self.test_la_1ere_guadeloupe_scraper()
        self.test_karibinfo_scraper()
        
        print("\n🔄 SCRAPERS INTEGRATION")
        self.test_all_scrapers_working()
        
        print("\n💾 INTELLIGENT CACHING SYSTEM")
        self.test_intelligent_caching_system()
        self.test_cache_invalidation()
        self.test_cache_warming()
        
        print("\n🚀 SCRAPING OPERATIONS")
        self.test_scrape_now_with_cache_clearing()
        self.test_scrape_status()
        
        print("\n" + "=" * 80)
        print("🔍 SCRAPERS TEST SUMMARY")
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 ALL SCRAPERS AND CACHING: OPERATIONAL")
            print("✅ All scrapers working with intelligent caching system")
        else:
            print("⚠️ SOME SCRAPERS HAVE ISSUES")
            print("❌ Review failed tests for scraper problems")
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = ScrapersAPITester()
    success = tester.run_all_scraper_tests()
    sys.exit(0 if success else 1)