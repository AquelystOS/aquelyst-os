#!/usr/bin/env python3
"""
AqueLyst Hunter - Quick Start Script

Run this script to start the app:
    python3 run_app.py

Or use the convenience methods below.
"""

import os
import sys
import subprocess
from pathlib import Path

# Get the directory this script is in
SCRIPT_DIR = Path(__file__).parent.absolute()
os.chdir(SCRIPT_DIR)

def check_python_version():
    """Check Python 3.11+."""
    if sys.version_info < (3, 11):
        print("❌ Python 3.11+ required")
        print(f"   Your version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")

def check_dependencies():
    """Check if dependencies are installed."""
    try:
        import streamlit
        import pandas
        import requests
        print("✅ Dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install -r requirements.txt")
        return False

def init_database():
    """Initialize database if not exists."""
    import database
    if not Path("aquelyst_hunter.db").exists():
        print("📁 Initializing database...")
        database.init_db()
        print("✅ Database created")
    else:
        print("✅ Database exists")

def start_app():
    """Start Streamlit app."""
    print("\n🚀 Starting AqueLyst Hunter...\n")
    print("📊 Dashboard: http://localhost:8501")
    print("💡 Tip: Load sample data from Settings tab\n")

    try:
        subprocess.run([
            "streamlit", "run", "app.py",
            "--logger.level=warning"
        ])
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)

def main():
    """Main startup sequence."""
    print("\n" + "=" * 50)
    print("🎯 AqueLyst Hunter")
    print("   Local Sales Management System")
    print("=" * 50 + "\n")

    # Checks
    check_python_version()
    if not check_dependencies():
        sys.exit(1)

    init_database()

    # Ready
    print("\n✅ All systems ready\n")

    # Start
    start_app()

if __name__ == "__main__":
    main()
