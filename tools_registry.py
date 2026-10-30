"""One list describing every page of the site. A tool with ready=True gets a route, a nav link, a homepage card,
a sitemap entry and its SEO tags. To add a tool later: set ready=True, add templates/tools/<slug>.html,
static/<slug>.js and its endpoints in tools_api.py."""
import os

SITE = {"name": "Gridglass", "url": os.environ.get("SITE_URL", "https://gridglass.in")}

HOME = {
    "title": "Gridglass – Free Online Excel and CSV Viewer, Filter and Pivot Table",
    "description": "Open Excel and CSV files in your browser. Search, filter, build pivot tables and export to xlsx, csv or pdf. "
                   "Plus free tools to clean data, compare files and make charts.",
    "name": "Gridglass",
}

TOOLS = [
    {"slug": "viewer", "name": "Spreadsheet Viewer", "path": "/viewer", "template": "viewer.html", "ready": True,
     "tagline": "Open a sheet, search and filter it, build pivot tables and export to xlsx, csv or pdf.",
     "title": "Excel and CSV Viewer – Search, Filter and Pivot Tables Online | Gridglass",
     "description": "View Excel and CSV files in your browser. Search every column, filter with Excel-style value lists, "
                    "build pivot tables and export the result to xlsx, csv or pdf.",
     "icon": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>'},
    {"slug": "data-cleaner", "name": "Data Cleaner", "ready": True,
     "tagline": "Trim spaces, remove duplicates and empty rows, fix case, fill gaps and convert types.",
     "title": "Data Cleaner – Clean Excel and CSV Data Online | Gridglass",
     "description": "Clean spreadsheet data online: remove duplicates and empty rows, trim spaces, fix text case, fill missing values, "
                    "find and replace, convert types and export the cleaned file as xlsx or csv.",
     "icon": '<path d="M4 20l9-9"/><path d="M13 11l-2-2 6-6 2 2z"/><path d="M5 5l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>'},
    {"slug": "compare-files", "name": "Compare Files", "ready": True,
     "tagline": "Find added, removed and changed rows between two Excel or CSV files.",
     "title": "Compare Excel and CSV Files – Find Differences Online | Gridglass",
     "description": "Compare two Excel or CSV files by key column or row position. See added, removed and changed rows "
                    "and every changed cell, then download the difference report as xlsx or csv.",
     "icon": '<rect x="3" y="4" width="10" height="14" rx="2"/><rect x="11" y="6" width="10" height="14" rx="2"/>'},
    {"slug": "chart-maker", "name": "Chart Maker", "ready": True,
     "tagline": "Turn a spreadsheet into bar, line, area, pie, scatter and histogram charts.",
     "title": "Chart Maker – Create Charts from Excel and CSV Online | Gridglass",
     "description": "Make bar, line, area, pie, donut, scatter and histogram charts from Excel or CSV data. "
                    "Group and aggregate columns, then download the chart as PNG or SVG.",
     "icon": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'},
    {"slug": "merge-files", "name": "Merge Files", "ready": False, "tagline": "", "title": "", "description": "", "icon": ""},
    {"slug": "data-profiler", "name": "Data Profiler", "ready": False, "tagline": "", "title": "", "description": "", "icon": ""},
    {"slug": "report-generator", "name": "Report Generator", "ready": False, "tagline": "", "title": "", "description": "", "icon": ""},
]


for _t in TOOLS:  # every page has a path and a template unless it says otherwise
    _t.setdefault("path", f"/tools/{_t['slug']}")
    _t.setdefault("template", f"tools/{_t['slug']}.html")


def ready_tools():
    return [t for t in TOOLS if t["ready"]]
