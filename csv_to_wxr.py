#!/usr/bin/env python3
"""Convert an inventory CSV into a WordPress WXR import file.

Default mappings:
- Model -> post title
- Description -> post content intro
- Quantity -> post meta custom field

Optional enhancements for inventory SEO/AEO:
- Generates item-specific slugs (e.g. /inventory/nokia-g-240g-a/)
- Renders remaining CSV columns as a technical specification HTML table
- Adds condition tags from a CSV column (or default value)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"
NS_WFW = "http://wellformedweb.org/CommentAPI/"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_WP = "http://wordpress.org/export/1.2/"

ET.register_namespace("content", NS_CONTENT)
ET.register_namespace("wfw", NS_WFW)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("wp", NS_WP)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-") or "inventory-item"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert inventory CSV into a WordPress WXR XML file."
    )
    parser.add_argument("csv_input", type=Path, help="Path to inventory CSV")
    parser.add_argument("wxr_output", type=Path, help="Path to write WXR XML")
    parser.add_argument("--site-url", required=True, help="WordPress site URL")
    parser.add_argument(
        "--base-path",
        default="inventory",
        help="Base URL path for imported posts (default: inventory)",
    )
    parser.add_argument(
        "--cpt",
        default="inventory_item",
        help="WordPress custom post type slug (default: inventory_item)",
    )
    parser.add_argument(
        "--title-column",
        default="Model",
        help="CSV column used as post title (default: Model)",
    )
    parser.add_argument(
        "--description-column",
        default="Description",
        help="CSV column used as content intro (default: Description)",
    )
    parser.add_argument(
        "--quantity-column",
        default="Quantity",
        help="CSV column stored as custom field quantity (default: Quantity)",
    )
    parser.add_argument(
        "--condition-column",
        default=None,
        help="CSV column used for post_tag condition labels (e.g. Used-Tested)",
    )
    parser.add_argument(
        "--default-condition",
        default="Used-Tested",
        help="Fallback condition tag when --condition-column is empty (default: Used-Tested)",
    )
    parser.add_argument(
        "--post-status",
        choices=["draft", "publish", "private", "pending"],
        default="draft",
        help="WordPress status for imported posts (default: draft)",
    )
    return parser.parse_args(argv)


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def build_specs_table(row: dict[str, str], used_columns: set[str]) -> str:
    spec_rows = []
    for key, value in row.items():
        if key in used_columns:
            continue
        cleaned_value = normalize_text(value)
        if not cleaned_value:
            continue
        spec_rows.append(
            "<tr>"
            f"<th>{html.escape(key)}</th>"
            f"<td>{html.escape(cleaned_value)}</td>"
            "</tr>"
        )

    if not spec_rows:
        return ""

    return (
        '<h2>Technical Specifications</h2>'
        '<table class="inventory-specs">'
        '<thead><tr><th>Specification</th><th>Value</th></tr></thead>'
        f"<tbody>{''.join(spec_rows)}</tbody>"
        "</table>"
    )


def build_content(description: str, specs_html: str, condition: str) -> str:
    badge_html = (
        '<p><strong>Condition:</strong> '
        f'<span class="condition-badge">{html.escape(condition)}</span></p>'
    )
    description_html = f"<p>{html.escape(description)}</p>" if description else ""
    return description_html + badge_html + specs_html


def append_text(parent: ET.Element, tag: str, text: str, namespace: str | None = None) -> ET.Element:
    element_name = f"{{{namespace}}}{tag}" if namespace else tag
    elem = ET.SubElement(parent, element_name)
    elem.text = text
    return elem


def add_wp_meta(item: ET.Element, key: str, value: str) -> None:
    postmeta = ET.SubElement(item, f"{{{NS_WP}}}postmeta")
    append_text(postmeta, "meta_key", key, NS_WP)
    append_text(postmeta, "meta_value", value, NS_WP)


def create_wxr(
    rows: Iterable[dict[str, str]],
    *,
    site_url: str,
    base_path: str,
    cpt: str,
    title_column: str,
    description_column: str,
    quantity_column: str,
    condition_column: str | None,
    default_condition: str,
    post_status: str,
) -> ET.ElementTree:
    now = dt.datetime.now(dt.timezone.utc)
    rfc2822 = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    w3c = now.strftime("%Y-%m-%d %H:%M:%S")

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:excerpt": "http://wordpress.org/export/1.2/excerpt/",
            "xmlns:wfw": NS_WFW,
        },
    )
    channel = ET.SubElement(rss, "channel")
    append_text(channel, "title", "Inventory Import")
    append_text(channel, "link", site_url.rstrip("/"))
    append_text(channel, "description", "Generated by csv_to_wxr.py")
    append_text(channel, "pubDate", rfc2822)
    append_text(channel, "language", "en-US")
    append_text(channel, "wxr_version", "1.2", NS_WP)
    append_text(channel, "base_site_url", site_url.rstrip("/"), NS_WP)
    append_text(channel, "base_blog_url", site_url.rstrip("/"), NS_WP)

    used_columns = {title_column, description_column, quantity_column}
    if condition_column:
        used_columns.add(condition_column)

    for idx, row in enumerate(rows, start=1):
        title = normalize_text(row.get(title_column))
        if not title:
            continue

        description = normalize_text(row.get(description_column))
        quantity = normalize_text(row.get(quantity_column))
        condition = (
            normalize_text(row.get(condition_column))
            if condition_column
            else default_condition
        ) or default_condition

        slug = slugify(title)
        specs_html = build_specs_table(row, used_columns)
        content = build_content(description, specs_html, condition)

        item = ET.SubElement(channel, "item")
        append_text(item, "title", title)
        append_text(item, "link", f"{site_url.rstrip('/')}/{base_path.strip('/')}/{slug}/")
        append_text(item, "pubDate", rfc2822)
        append_text(item, "creator", "csv_to_wxr", NS_DC)
        append_text(item, "guid", f"inventory-{idx}")
        append_text(item, "description", "")
        append_text(item, "encoded", content, NS_CONTENT)
        append_text(item, "post_id", str(idx), NS_WP)
        append_text(item, "post_date", w3c, NS_WP)
        append_text(item, "post_date_gmt", w3c, NS_WP)
        append_text(item, "comment_status", "closed", NS_WP)
        append_text(item, "ping_status", "closed", NS_WP)
        append_text(item, "post_name", slug, NS_WP)
        append_text(item, "status", post_status, NS_WP)
        append_text(item, "post_parent", "0", NS_WP)
        append_text(item, "menu_order", "0", NS_WP)
        append_text(item, "post_type", cpt, NS_WP)
        append_text(item, "post_password", "", NS_WP)
        append_text(item, "is_sticky", "0", NS_WP)

        category = ET.SubElement(
            item,
            "category",
            {
                "domain": "post_tag",
                "nicename": slugify(condition),
            },
        )
        category.text = condition

        add_wp_meta(item, "quantity", quantity)

    return ET.ElementTree(rss)


def indent_xml(elem: ET.Element, level: int = 0) -> None:
    indent = "  "
    i = "\n" + level * indent
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + indent
        for child in elem:
            indent_xml(child, level + 1)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV appears to have no header row.")
        return list(reader)


def validate_columns(rows: list[dict[str, str]], required_columns: list[str]) -> None:
    if not rows:
        raise ValueError("CSV contains no data rows.")

    headers = set(rows[0].keys())
    missing = [col for col in required_columns if col not in headers]
    if missing:
        raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    rows = read_csv_rows(args.csv_input)

    required_columns = [args.title_column, args.description_column, args.quantity_column]
    if args.condition_column:
        required_columns.append(args.condition_column)
    validate_columns(rows, required_columns)

    tree = create_wxr(
        rows,
        site_url=args.site_url,
        base_path=args.base_path,
        cpt=args.cpt,
        title_column=args.title_column,
        description_column=args.description_column,
        quantity_column=args.quantity_column,
        condition_column=args.condition_column,
        default_condition=args.default_condition,
        post_status=args.post_status,
    )
    indent_xml(tree.getroot())

    args.wxr_output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.wxr_output, encoding="utf-8", xml_declaration=True)

    print(f"WXR export complete: {args.wxr_output} ({len(rows)} CSV rows processed)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 - clear CLI error for users
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
