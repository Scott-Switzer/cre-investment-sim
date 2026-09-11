#!/usr/bin/env python3
"""
One-command startup script for the REAL 605 CRE Simulator.

This script:
1. Validates the environment
2. Bootstraps demo data
3. Performs a lightweight app preflight
4. Launches Streamlit through the project interpreter

Run with: uv run python scripts/run_demo.py
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'=' * 60}")
    print(f"{description}")
    print(f"{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"\n❌ FAILED: {description}")
        return False
    
    print(f"\n✅ SUCCESS: {description}")
    return True


def main():
    """Run the complete startup sequence."""
    print("=" * 60)
    print("REAL 605 CRE Simulator - One-Command Startup")
    print("=" * 60)
    
    py = sys.executable  # Always use the project Python
    here = Path(__file__).resolve().parent
    
    # Step 1: Verify environment
    if not run_command(
        [py, str(here / "verify_environment.py")],
        "Step 1: Verifying Environment"
    ):
        print("\n❌ Environment verification failed. Please check your Python installation.")
        sys.exit(1)
    
    # Step 2: Bootstrap demo data
    if not run_command(
        [py, str(here / "bootstrap_demo.py")],
        "Step 2: Bootstrapping Demo Data"
    ):
        print("\n❌ Demo data bootstrap failed.")
        sys.exit(1)
    
    # Step 3: Run tests (optional but recommended)
    print(f"\n{'=' * 60}")
    print("Step 3: Running Tests (Optional)")
    print(f"{'=' * 60}")
    print(f"Running: python -m pytest tests/ -q")
    print()
    
    test_result = subprocess.run(
        [py, "-m", "pytest", "tests/", "-q"],
        capture_output=False
    )
    
    if test_result.returncode != 0:
        print("\n⚠️  WARNING: Tests failed, but continuing to launch...")
    else:
        print("\n✅ Tests passed")
    
    # Step 4: Launch Streamlit
    print(f"\n{'=' * 60}")
    print("Step 4: Launching Streamlit")
    print(f"{'=' * 60}")
    print("Running: python -m streamlit run app.py")
    print()
    print("The application will open in your browser at http://localhost:8501")
    print("Press Ctrl+C to stop the server.")
    print()
    
    # Launch Streamlit (this will block)
    subprocess.run([py, "-m", "streamlit", "run", "app.py"])


if __name__ == "__main__":
    main()
