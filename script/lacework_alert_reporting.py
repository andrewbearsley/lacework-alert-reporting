#!/usr/bin/env python3
"""
Lacework Alert Reporting Script - Wrapper

This is a wrapper script that delegates to the modular implementation.
It maintains the same interface and command-line arguments as the original script.

The actual implementation is now in the modules/ directory for better maintainability.
"""

import sys
from pathlib import Path

# Add the modules directory to the Python path
    script_dir = Path(__file__).parent
modules_dir = script_dir / "modules"
sys.path.insert(0, str(modules_dir))

# Import and run the main function from the modular implementation
from main import main

if __name__ == "__main__":
    main()
