"""
Regression tests for Streamlit Cloud compatibility bugs.

These tests prove the fixes for:
- Invalid st.link() API calls (replace with st.page_link)
- Invalid pdk.Deck(title=...) argument
- Missing primary_risk field in PropertyRow/property data
- Pages registry key mismatches

Run: uv run python -m pytest tests/test_cloud_compatibility.py -v
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNoStLinkCalls(unittest.TestCase):
    """Prove the repository contains ZERO st.link() calls."""

    def test_no_st_link_in_pages(self):
        """All pages/ files must not contain st.link()."""
        pages_dir = os.path.join(os.path.dirname(__file__), '..', 'pages')
        for filename in os.listdir(pages_dir):
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(pages_dir, filename)
            with open(filepath) as f:
                content = f.read()
            matches = re.findall(r'st\.link\s*\(', content)
            self.assertEqual(
                len(matches),
                0,
                f"{filename} contains {len(matches)} st.link() call(s): {matches}",
            )

    def test_no_st_link_in_app(self):
        """app.py must not contain st.link()."""
        app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
        with open(app_path) as f:
            content = f.read()
        matches = re.findall(r'st\.link\s*\(', content)
        self.assertEqual(
            len(matches),
            0,
            f"app.py contains {len(matches)} st.link() call(s)",
        )

    def test_no_st_link_in_src(self):
        """src/ files must not contain st.link()."""
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, _dirs, files in os.walk(src_dir):
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                filepath = os.path.join(root, filename)
                with open(filepath) as f:
                    content = f.read()
                matches = re.findall(r'st\.link\s*\(', content)
                self.assertEqual(
                    len(matches),
                    0,
                    f"{os.path.relpath(filepath, os.path.join(os.path.dirname(__file__), '..'))} contains st.link()",
                )


class TestPyDeckInstantiation(unittest.TestCase):
    """Prove the geospatial map can instantiate under installed pydeck."""

    def test_pydeck_property_map(self):
        """pydeck_property_map() must not raise on valid data."""
        import pandas as pd
        from src.geo.mapping import pydeck_property_map

        # Minimal valid dataframe with all columns the mapping function needs
        df = pd.DataFrame([
            {
                'property_id': 'TEST-001',
                'property_name': 'Test Property',
                'type': 'Industrial',
                'submarket': 'Test Submarket',
                'lat': 34.0522,
                'lon': -118.2437,
                'size_sf': 10000,
                'asking_price': 5000000,
                'current_noi': 250000,
                'going_in_cap': 0.05,
                'occupancy': 0.95,
            }
        ])

        deck = pydeck_property_map(df, lat_col="lat", lon_col="lon")
        self.assertIsNotNone(deck)
        # Verify it's a pydeck Deck instance
        import pydeck
        self.assertIsInstance(deck, pydeck.Deck)


class TestPropertyDataFields(unittest.TestCase):
    """Prove generated property data contains all fields required by Deal Room and Investment Decision."""

    def test_property_row_has_primary_risk(self):
        """PropertyRow dataclass must have primary_risk field."""
        from dataclasses import fields
        from src.data.properties import PropertyRow

        field_names = [f.name for f in fields(PropertyRow)]
        self.assertIn('primary_risk', field_names, 'PropertyRow missing primary_risk field')

    def test_generate_properties_has_primary_risk(self):
        """generate_properties DataFrame must contain primary_risk column."""
        from src.data.properties import generate_properties

        df = generate_properties(seed=42)
        self.assertIn('primary_risk', df.columns, 'properties DataFrame missing primary_risk column')
        self.assertFalse(df['primary_risk'].isna().any(), 'primary_risk has NaN values')

    def test_deal_room_fields_all_present(self):
        """Deal Room renders property table with all fields including primary_risk."""
        from src.data.properties import generate_properties

        df = generate_properties(seed=42)
        # Deal Room lists these columns in its table rendering
        deal_room_cols = [
            'property_id', 'property_name', 'type', 'submarket', 'size_sf',
            'units', 'asking_price', 'current_noi', 'going_in_cap', 'occupancy',
            'walt', 'market_rent', 'in_place_rent', 'tenant_concentration',
            'debt_rate', 'amortization_years', 'max_ltv', 'property_quality',
            'lease_expiry_profile', 'primary_risk',
        ]
        for col in deal_room_cols:
            self.assertIn(col, df.columns, f'Deal Room field "{col}" missing from property data')

    def test_investment_decision_fields_all_present(self):
        """Investment Decision accesses primary_risk without KeyError."""
        from src.data.properties import generate_properties

        df = generate_properties(seed=42)
        # Investment Decision reads p['primary_risk']
        for _, row in df.head(3).iterrows():
            # This will raise KeyError if field is missing
            _ = row['primary_risk']


class TestPageImports(unittest.TestCase):
    """Prove all page modules can be imported without AttributeError/KeyError."""

    def test_valuation_lab_import(self):
        """valuation_lab module must import without crash."""
        from pages import valuation_lab
        self.assertTrue(hasattr(valuation_lab, 'show'))

    def test_geospatial_import(self):
        """geospatial module must import without crash."""
        from pages import geospatial
        self.assertTrue(hasattr(geospatial, 'show'))

    def test_deal_room_import(self):
        """deal_room module must import without crash."""
        from pages import deal_room
        self.assertTrue(hasattr(deal_room, 'show'))

    def test_investment_decision_import(self):
        """investment_decision module must import without crash."""
        from pages import investment_decision
        self.assertTrue(hasattr(investment_decision, 'show'))

    def test_data_quality_import(self):
        """data_quality module must import without crash."""
        from pages import data_quality
        self.assertTrue(hasattr(data_quality, 'show'))

    def test_sql_lab_import(self):
        """sql_lab module must import without crash."""
        from pages import sql_lab
        self.assertTrue(hasattr(sql_lab, 'show'))

    def test_pages_registry_complete(self):
        """All imported page modules must be in __all__."""
        from pages import __all__ as page_names
        import pages as pages_mod

        for name in page_names:
            self.assertTrue(hasattr(pages_mod, name), f'Page "{name}" in __all__ but not importable')

    def test_pages_no_keyerror(self):
        """pages registry must not raise KeyError on any key."""
        import pages
        for name in pages.__all__:
            try:
                _ = getattr(pages, name)
            except AttributeError as e:
                self.fail(f'pages.{name} raises AttributeError: {e}')


if __name__ == '__main__':
    unittest.main()
