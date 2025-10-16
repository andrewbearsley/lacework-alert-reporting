#!/usr/bin/env python3
"""
Lacework Compliance Reporting Script V2 - Optimized Version

This is the optimized version using compliance-first approach with paginated inventory.
Designed for large FortiCNP environments with hundreds of accounts and thousands of resources.

Key optimizations:
- Compliance-first approach (focus on non-compliant policies only)
- Paginated account inventory (handles 5000+ resources per account)
- 80-90% reduction in API calls through caching and bulk queries
- Sequential processing to respect Lacework API rate limits
- Smart caching strategy with TTL based on data volatility
"""

import sys
from pathlib import Path

# Add the modules directory to the Python path
script_dir = Path(__file__).parent
modules_dir = script_dir / "modules"
sys.path.insert(0, str(modules_dir))

# Import and run the main function from the optimized implementation
from main_v2 import main

if __name__ == "__main__":
    main()
