# Gridglass

A spreadsheet viewer and a set of tools for Excel and CSV files (Flask, Polars, DuckDB).

| URL | What it does |
| --- | --- |
| `/` | Upload once, then pick a tool |
| `/viewer` | Spreadsheet viewer: search, filter, pivot tables, export xlsx / csv / pdf |
| `/tools/data-cleaner` | Step-by-step cleaning; the cleaned data can be kept as a new file |
| `/tools/compare-files` | Added, removed and changed rows between two open files, with an Excel report |
| `/tools/chart-maker` | Bar, line, area, pie, donut, scatter and histogram charts; PNG, SVG and csv export |

**Upload once.** Files are added to a *workspace* (up to 5 files). Every page uses the workspace, and the browser remembers it
while the server keeps it (2 hours of inactivity). The header row is set per sheet in the bar at the top of each page
and applies to every tool.

## Run locally
```
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                                          # http://127.0.0.1:5000
python scripts/smoke_test.py                           # optional end-to-end check
```

## Project layout
```
app.py              Flask app: viewer API (/api/query, /api/values, /api/export), page routes, sitemap, robots
engine.py           shared: file reading, type detection, SQL quoting, xlsx / csv writers
workspace.py        the workspace: uploaded files in one DuckDB database, /api/ws/* endpoints
tools_registry.py   one list of all pages (name, path, SEO title and description, ready flag)
tools_api.py        /api/tools/*: Data Cleaner, Compare Files, Chart Maker
templates/          base.html, index.html (home), viewer.html, _cards.html, tools/<slug>.html
static/             common.js, workspace.js (shared), tools.js (tool widgets), app.js (viewer), home.js, one JS per tool, style.css
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
3. Add its endpoints to `tools_api.py`. Read the open sheet with `workspace.sheet_df(...)` and use `WS`, `ColPicker`, `tableHTML` and `download` in the page script.

The route, navigation link, homepage card, footer link and sitemap entry appear automatically.

## Notes
- Uploaded data lives in memory only (two hours after the last activity). Run **one** gunicorn worker (as in `render.yaml`) because sessions are not shared between processes.
