import csv
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class CsvToWxrCliTests(unittest.TestCase):
    def test_generates_wxr_with_expected_mappings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            csv_path = tmp / "inventory.csv"
            out_path = tmp / "inventory.xml"

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "Model",
                        "Description",
                        "Quantity",
                        "Condition",
                        "Manufacturer",
                        "Port Count",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Model": "Nokia G-240G-A",
                        "Description": "GPON ONT for fiber deployments",
                        "Quantity": "12",
                        "Condition": "Refurbished",
                        "Manufacturer": "Nokia",
                        "Port Count": "4",
                    }
                )

            result = subprocess.run(
                [
                    sys.executable,
                    "csv_to_wxr.py",
                    str(csv_path),
                    str(out_path),
                    "--site-url",
                    "https://logicnetworks.com",
                    "--condition-column",
                    "Condition",
                    "--post-status",
                    "publish",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(out_path.exists())

            tree = ET.parse(out_path)
            root = tree.getroot()

            ns = {
                "content": "http://purl.org/rss/1.0/modules/content/",
                "wp": "http://wordpress.org/export/1.2/",
            }

            item = root.find("./channel/item")
            self.assertIsNotNone(item)
            self.assertEqual(item.findtext("title"), "Nokia G-240G-A")
            self.assertEqual(
                item.findtext("link"),
                "https://logicnetworks.com/inventory/nokia-g-240g-a/",
            )
            self.assertEqual(item.findtext("wp:post_type", namespaces=ns), "inventory_item")
            self.assertEqual(item.findtext("wp:status", namespaces=ns), "publish")

            content = item.findtext("content:encoded", namespaces=ns)
            self.assertIn("Technical Specifications", content)
            self.assertIn("condition-badge", content)
            self.assertIn("Refurbished", content)

            self.assertEqual(
                item.findtext("wp:postmeta/wp:meta_key", namespaces=ns),
                "quantity",
            )
            self.assertEqual(
                item.findtext("wp:postmeta/wp:meta_value", namespaces=ns),
                "12",
            )

    def test_fails_when_required_column_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            csv_path = tmp / "inventory_missing.csv"
            out_path = tmp / "inventory.xml"

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Model", "Description"])  # no Quantity
                writer.writeheader()
                writer.writerow({"Model": "A", "Description": "B"})

            result = subprocess.run(
                [
                    sys.executable,
                    "csv_to_wxr.py",
                    str(csv_path),
                    str(out_path),
                    "--site-url",
                    "https://logicnetworks.com",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing required CSV columns", result.stderr)


if __name__ == "__main__":
    unittest.main()
