# CSV to WordPress (WXR) Exporter

`csv_to_wxr.py` converts an inventory CSV into a WordPress WXR import file so you can bulk-import product/inventory pages into WordPress (including Avada-based sites).

## What it does

- Maps **Model** → post title.
- Maps **Description** → post content intro paragraph.
- Maps **Quantity** → `quantity` custom field (`wp:postmeta`).
- Builds item-specific slugs (`/inventory/<model-slug>/`).
- Renders all remaining CSV columns into a **Technical Specifications** HTML `<table>`.
- Adds a condition tag (default: `Used-Tested`, or from an optional CSV column).

## Requirements

- Python 3.9+

## Usage

```bash
python3 csv_to_wxr.py inventory.csv output/inventory.xml --site-url https://logicnetworks.com
```

### Optional arguments

- `--cpt inventory_item` (default)
- `--base-path inventory` (default)
- `--post-status draft|publish|private|pending`
- `--condition-column Condition`
- `--default-condition Used-Tested`
- `--title-column Model`
- `--description-column Description`
- `--quantity-column Quantity`

## Browser UI (bulk CSV + single part)

If you want a visual workflow instead of terminal commands, run the local UI:

```bash
python3 inventory_ui.py --host 127.0.0.1 --port 8787
```

Then open:

```text
http://127.0.0.1:8787
```

The UI provides two flows:

1. **Bulk CSV → WXR**: Upload a large CSV and download a ready-to-import WXR.
2. **Single Part → WXR**: Fill one part form (with optional specs JSON) and download a one-item WXR.

After download, import in WordPress via **Tools → Import → WordPress**.

## Quick testing ("slash test")

If by "slash test" you mean quickly validating end-to-end from terminal, run:

```bash
make test
```

This executes the automated unit/CLI tests in `tests/test_csv_to_wxr.py` and verifies:

- WXR generation with expected field mapping and slug format.
- Condition tag/badge and technical spec table presence.
- Failure behavior when required CSV headers are missing.

If you prefer a manual one-off run:

```bash
python3 csv_to_wxr.py inventory.csv output/inventory.xml --site-url https://logicnetworks.com
```

## WordPress import flow

1. In WordPress Admin, go to **Tools → Import**.
2. Choose the WordPress importer.
3. Upload the generated XML file.
4. Assign authors and run the import.
5. Apply your Avada layout/template to the imported CPT posts.

## Example CSV headers

```csv
Model,Description,Quantity,Condition,Manufacturer,Port Count,Form Factor
```

In this example, `Manufacturer`, `Port Count`, and `Form Factor` appear in the generated technical specs table for each post.
