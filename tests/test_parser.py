from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "actualizar_radares_smn.py"

spec = importlib.util.spec_from_file_location(
    "actualizar_radares_smn",
    SCRIPT_PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RadarParserTests(unittest.TestCase):
    def test_extract_token(self) -> None:
        html = (
            "<script>"
            "localStorage.setItem('token', "
            "'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXJhZGFyIn0.abcdefghijklmnopqrstuvwxyz0123456789');"
            "</script>"
        )
        self.assertEqual(
            module.extract_token(html),
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXJhZGFyIn0.abcdefghijklmnopqrstuvwxyz0123456789",
        )

    def test_parse_products_from_options(self) -> None:
        html = """
        <select>
          <option value="COMP_ARG">Mosaico Argentina</option>
          <option value="RMA2_240">Ezeiza (Buenos Aires)</option>
        </select>
        """
        products = module.parse_products_from_page(html)
        self.assertEqual(products["COMP_ARG"], "Mosaico Argentina")
        self.assertEqual(
            products["RMA2_240"],
            "Ezeiza (Buenos Aires)",
        )

    def test_parse_frame(self) -> None:
        frame = module.parse_frame(
            "RMA2_240_20260702_052021Z.png"
        )
        self.assertIsNotNone(frame)
        self.assertEqual(
            frame["timestamp_utc"],
            "2026-07-02T05:20:21Z",
        )
        self.assertTrue(
            frame["url"].endswith(
                "RMA2_240_20260702_052021Z.png"
            )
        )

    def test_official_page_can_correct_fallback_id(self) -> None:
        config = {
            "products": [
                {
                    "id": "RMA99_240",
                    "name": "Santa Isabel",
                    "type": "radar",
                    "province": "La Pampa",
                    "order": 1,
                }
            ]
        }
        merged = module.merge_products(
            config,
            {"RMA18_240": "Santa Isabel (La Pampa)"},
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "RMA18_240")
        self.assertEqual(merged[0]["fallback_id"], "RMA99_240")


if __name__ == "__main__":
    unittest.main()
