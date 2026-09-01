from __future__ import annotations

import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class DistributionMetadataTest(unittest.TestCase):
    def test_manifest_declares_public_surface_and_mit_license(self):
        manifest = (PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8")
        for declaration in (
            "api_version: 1",
            "license: MIT",
            "  - discord_thread_links",
            "  - transform_llm_output",
            "  - pre_gateway_dispatch",
            "  - gateway_control_message",
            "  - gateway_history_message",
        ):
            self.assertIn(declaration, manifest)

        license_text = (PLUGIN_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 Chris A. Kim", license_text)


if __name__ == "__main__":
    unittest.main()
