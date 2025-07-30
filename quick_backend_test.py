#!/usr/bin/env python3
"""
Quick Backend API Test for Guadeloupe Veille Média
"""

import requests
import sys
from datetime import datetime

def test_api_endpoint(url, name, timeout=10):
    """Test a single API endpoint"""
    try:
        response = requests.get(url, timeout=timeout)
        success = response.status_code == 200
        
        if success:
            try:
                data = response.json()
                if data.get('success'):
                    print(f"✅ {name} - PASSED")
                    return True
                else:
                    print(f"❌ {name} - API returned success=False")
                    return False
            except:
                print(f"❌ {name} - Invalid JSON response")
                return False
        else:
            print(f"❌ {name} - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {name} - Error: {str(e)}")
        return False

def main():
    base_url = "https://2b90a2f6-8c6b-4335-a643-12cd029b2682.preview.emergentagent.com"
    
    print("🏝️ Quick Guadeloupe Veille Média API Test")
    print(f"📡 Testing: {base_url}")
    print("=" * 50)
    
    tests = [
        (f"{base_url}/api/dashboard-stats", "Dashboard Stats"),
        (f"{base_url}/api/articles", "Get Articles"),
        (f"{base_url}/api/transcriptions", "Get Transcriptions"),
        (f"{base_url}/api/digest", "Get Digest"),
        (f"{base_url}/api/scheduler/status", "Scheduler Status"),
    ]
    
    passed = 0
    total = len(tests)
    
    for url, name in tests:
        if test_api_endpoint(url, name):
            passed += 1
    
    print("=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All core API endpoints working!")
        return 0
    else:
        print(f"⚠️ {total - passed} endpoints failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())