"""
Render smoke tests — format helpers, config, and number_input audit.

Run: uv run python -m pytest tests/test_render_smoke.py -v

These tests catch the exact class of production crashes that
happened with invalid st.number_input(format="%.0f%%") calls.
The GameManager lifecycle tests live in test_final_verification.py.
"""

from __future__ import annotations
import sys
import os
import re
import subprocess
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFormatHelpers(unittest.TestCase):
    """Format helpers return valid strings."""

    def test_fmt_currency(self):
        from app import fmt_currency
        self.assertEqual(fmt_currency(0), "$0.0M")
        self.assertEqual(fmt_currency(47.5), "$47.5M")

    def test_fmt_pct(self):
        from app import fmt_pct
        self.assertEqual(fmt_pct(0.0), "0.0%")
        self.assertEqual(fmt_pct(0.057), "5.7%")

    def test_fmt_delta(self):
        from app import fmt_delta
        self.assertEqual(fmt_delta(5.0), "+$5.0M")
        self.assertEqual(fmt_delta(-3.2), "$-3.2M")

    def test_round_interpretation(self):
        from app import round_interpretation
        interp = round_interpretation("Test Property", 50.0, 48.0, 52.0, True)
        self.assertIsInstance(interp, str)
        self.assertTrue(len(interp) > 0)


class TestNumberInputAudit(unittest.TestCase):
    """Verify NO st.number_input calls use invalid format strings."""

    def test_no_percent_literal_in_format(self):
        """All st.number_input calls must use valid printf formats."""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        r = subprocess.run(
            ["grep", "-rn", "st.number_input", project_root,
             "--include=*.py",
             "--exclude-dir=__pycache__",
             "--exclude-dir=.venv",
             "--exclude-dir=tests",
             "--exclude-dir=.agents"],
            capture_output=True, text=True, timeout=30, cwd=project_root
        )

        self.assertTrue(r.stdout, "No number_input calls found — check if app.py is empty")

        lines = r.stdout.strip().split("\n")
        invalid = []
        for line in lines:
            if "format=" not in line.lower():
                continue
            match = re.search(r'format\s*=\s*["\']([^"\']+)["\']', line)
            if match:
                fmt_str = match.group(1)
                if "%%" in fmt_str:
                    invalid.append((line.strip(), fmt_str))

        if invalid:
            msg = "Invalid format strings found:\n"
            for line, fmt in invalid:
                msg += f"  {line}\n    format: {fmt}\n"
            self.fail(msg)

    def test_valid_format_strings_exist(self):
        """Confirm valid formats ARE in use (regression guard)."""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        with open(os.path.join(project_root, "app.py")) as f:
            content = f.read()

        # These valid formats must exist
        self.assertIn('format="%0.1f"', content)
        self.assertIn('format="%0.0f"', content)
        self.assertIn('format="%.1f"', content)
        self.assertIn('format="%.2f"', content)


class TestConfigToml(unittest.TestCase):
    """Config file exists and has required settings."""

    def test_config_exists_and_valid(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".streamlit",
            "config.toml"
        )
        self.assertTrue(os.path.exists(config_path), "config.toml not found")

        with open(config_path) as f:
            content = f.read()

        self.assertIn("headless", content)
        self.assertIn("port", content)
        self.assertIn("showSidebarNavigation", content)


class TestImportValid(unittest.TestCase):
    """app.py and pages/ modules import without error."""

    def test_app_imports(self):
        import app  # noqa: F401

    def test_pages_import(self):
        import pages  # noqa: F401


if __name__ == "__main__":
    unittest.main(verbosity=2)
