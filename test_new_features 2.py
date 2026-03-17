#!/usr/bin/env python3
"""
Test runner specifically for new filtering and analytics features
"""

import sys
from backend_test import GuadeloupeMediaAPITester

def main():
    """Run tests specifically for new filtering and analytics features"""
    tester = GuadeloupeMediaAPITester()
    return tester.run_new_filtering_analytics_tests()

if __name__ == "__main__":
    sys.exit(main())