import unittest
import xml.etree.ElementTree as ET

from inventory_ui import _read_csv_dicts, _wxr_bytes


class InventoryUiHelpersTests(unittest.TestCase):
    def test_read_csv_dicts_validates_required_columns(self):
        data = b"Model,Description\nA,B\n"
        with self.assertRaisesRegex(ValueError, "Missing required CSV columns"):
            _read_csv_dicts(data)

    def test_wxr_bytes_for_single_row(self):
        rows = [
            {
                "Model": "Cisco 2960X",
                "Description": "Layer 2 switch",
                "Quantity": "7",
                "Condition": "Used-Tested",
                "Manufacturer": "Cisco",
            }
        ]
        content = _wxr_bytes(
            rows,
            site_url="https://logicnetworks.com",
            base_path="inventory",
            cpt="inventory_item",
            post_status="draft",
        )

        root = ET.fromstring(content)
        ns = {
            "content": "http://purl.org/rss/1.0/modules/content/",
            "wp": "http://wordpress.org/export/1.2/",
        }

        item = root.find("./channel/item")
        self.assertIsNotNone(item)
        self.assertEqual(item.findtext("title"), "Cisco 2960X")
        self.assertEqual(item.findtext("wp:post_type", namespaces=ns), "inventory_item")
        self.assertIn("Technical Specifications", item.findtext("content:encoded", namespaces=ns))


if __name__ == "__main__":
    unittest.main()
