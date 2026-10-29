# Gridglass

A spreadsheet viewer and a set of tools for Excel and CSV files (Flask, Polars, DuckDB).

| URL | What it does |
| --- | --- |
| `/` | Viewer: open files, search, filter, pivot tables, export xlsx / csv / pdf |
| `/tools/data-cleaner` | Step-by-step cleaning (trim, duplicates, empty rows, case, missing values, replace, convert, rename) |
| `/tools/compare-files` | Added, removed and changed rows between two files, with an Excel report |
| `/tools/chart-maker` | Bar, line, area, pie, donut, scatter and histogram charts; PNG, SVG and csv export |

## Run locally
```
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                          # http://127.0.0.1:5000
python scripts/smoke_test.py                           # optional end-to-end check
```

## Project layout
```
app.py              Flask app: viewer API, page routes, sitemap, robots, health check
engine.py           shared: file reading, type detection, SQL quoting, xlsx / csv writers
tools_registry.py   one list of all tools (name, SEO title and description, ready flag)
tools_api.py        /api/tools/*: upload, Data Cleaner, Compare Files, Chart Maker
templates/          base.html, index.html (viewer), _cards.html, tools/<slug>.html
static/             common.js (shared), tools.js (tool widgets), app.js (viewer), one JS per tool, style.css
render.yaml         Render blueprint
```

## Settings (environment variables)
| Name | Default | Meaning |
| --- | --- | --- |
| `SITE_URL` | `https://gridglass.in` | Used for canonical links and the sitemap |
| `MAX_UPLOAD_MB` | none | Largest upload in MB (set it on small servers) |
| `TOOL_MAX_ROWS` | `1000000` | Largest sheet the tools accept |

## Add another tool
1. In `tools_registry.py`, fill in the entry (tagline, title, description, icon) and set `ready` to `True`.
2. Add `templates/tools/<slug>.html` (copy an existing one) and `static/<slug>.js`.
3. Add its endpoints to `tools_api.py`. Use `Uploader`, `ColPicker`, `tableHTML` and `download` from `tools.js`.

The route, navigation link, homepage card, footer link and sitemap entry appear automatically.

## Notes
- Uploaded data lives in memory only (one hour for tools, two hours for the viewer). Run **one** gunicorn worker (as in `render.yaml`) because sessions are not shared between processes.
