#!/usr/bin/env python3
"""
Environment verification script.

Validates that the project's Python environment is correctly configured
with all required dependencies at compatible versions.

Run with: uv run python scripts/verify_environment.py
"""

import sys
from typing import Tuple, List


def check_python_version() -> Tuple[bool, str]:
    """Check that Python version is 3.11+."""
    major, minor = sys.version_info[:2]
    if major != 3 or minor < 11:
        return False, f"Python {major}.{minor} found, requires Python 3.11+"
    return True, f"Python {major}.{minor}.{sys.version_info[2]}"


def import_and_check(module_name: str, import_name: str = None) -> Tuple[bool, str]:
    """Attempt to import a module and return its version."""
    if import_name is None:
        import_name = module_name
    
    try:
        module = __import__(import_name)
        version = getattr(module, "__version__", "unknown")
        return True, f"{module_name} {version}"
    except ImportError as e:
        return False, f"{module_name} import failed: {e}"


def main():
    """Run all environment checks."""
    print("=" * 60)
    print("REAL 605 CRE Simulator - Environment Verification")
    print("=" * 60)
    print()
    
    # Check Python version
    print("Checking Python version...")
    python_ok, python_msg = check_python_version()
    print(f"  {python_msg}")
    if not python_ok:
        print("  ❌ FAIL: Python version requirement not met")
        sys.exit(1)
    print("  ✅ PASS")
    print()
    
    # Check interpreter location
    print("Checking interpreter location...")
    print(f"  Executable: {sys.executable}")
    if ".venv" not in sys.executable:
        print("  ❌ FAIL: Interpreter not in .venv")
        sys.exit(1)
    print("  ✅ PASS")
    print()
    
    # Check required dependencies
    print("Checking required dependencies...")
    dependencies = [
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("pandas", "pandas"),
        ("sklearn", "sklearn"),
        ("duckdb", "duckdb"),
        ("streamlit", "streamlit"),
        ("statsmodels", "statsmodels"),
        ("plotly", "plotly"),
        ("altair", "altair"),
        ("geopandas", "geopandas"),
    ]
    
    all_passed = True
    for display_name, import_name in dependencies:
        ok, msg = import_and_check(display_name, import_name)
        print(f"  {msg}")
        if not ok:
            print(f"    ❌ FAIL")
            all_passed = False
        else:
            print(f"    ✅ PASS")
    
    print()
    
    if all_passed:
        print("=" * 60)
        print("ENVIRONMENT CHECK: PASS")
        print("=" * 60)
        sys.exit(0)
    else:
        print("=" * 60)
        print("ENVIRONMENT CHECK: FAIL")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
