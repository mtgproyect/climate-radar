from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "manifiesto.json"
CONFIG_PATH = ROOT / "config" / "productos.json"


class RadarContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )
        self.config = json.loads(
            CONFIG_PATH.read_text(encoding="utf-8")
        )

    def test_expected_catalog_size(self) -> None:
        products = self.config["products"]
        mosaics = [
            item for item in products if item["type"] == "mosaic"
        ]
        radars = [
            item for item in products if item["type"] == "radar"
        ]

        self.assertEqual(len(products), 24)
        self.assertEqual(len(mosaics), 3)
        self.assertEqual(len(radars), 21)

    def test_product_ids_are_unique(self) -> None:
        ids = [item["id"] for item in self.config["products"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_manifest_storage_contract(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertTrue(self.manifest["enabled"])
        self.assertEqual(
            self.manifest["storage"]["mode"],
            "remote_urls_only",
        )
        self.assertEqual(
            self.manifest["storage"]["stored_image_count"],
            0,
        )

    def test_repository_contains_no_radar_images(self) -> None:
        extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        images = [
            path
            for path in ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
        ]
        self.assertEqual(images, [])

    def test_all_frame_urls_are_official_remote_urls(self) -> None:
        for product in self.manifest.get("products", []):
            for frame in product.get("frames", []):
                self.assertTrue(
                    frame["url"].startswith(
                        "https://estaticos.smn.gob.ar/"
                    )
                )


if __name__ == "__main__":
    unittest.main()
