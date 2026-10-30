"""End-to-end check of the workspace, the viewer and the three tools with the real libraries.
Run from the project folder:  python scripts/smoke_test.py"""
import io, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xlsxwriter
from app import app

c, results, WS = app.test_client(), [], {"ws": None}


def check(label, cond):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def xlsx(rows):
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet("Data")
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            ws.write(i, j, v)
    wb.close()
    return buf.getvalue()


def upload(data, name):
    """Add a file to the one shared workspace, exactly like the browser does."""
    form = {"file": (io.BytesIO(data), name)}
    if WS["ws"]:
        form["ws"] = WS["ws"]
    r = c.post("/api/ws/upload", data=form, content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 200, j
    WS["ws"] = j["ws"]
    f = next(x for x in j["files"] if x["id"] == j["file"])
    return {"ws": j["ws"], "file": f["id"], "sheet": f["sheets"][0]["id"], "meta": f["sheets"][0], "state": j}


def post(url, body):
    r = c.post(url, json=body)
    return r.status_code, (r.get_json() if r.is_json else r.data)


for path in ("/", "/viewer", "/tools/data-cleaner", "/tools/compare-files", "/tools/chart-maker", "/sitemap.xml", "/robots.txt", "/healthz"):
    check(f"GET {path}", c.get(path).status_code == 200)

# ---- upload once: one workspace, several files ----
sales = upload(b"Region;Units;Day\nNorth;5;2024-01-05\nSouth;7;2024-02-05\nNorth;3;2024-03-05\n", "sales.csv")
check("workspace: semicolon csv detected", [x["name"] for x in sales["meta"]["cols"]] == ["Region", "Units", "Day"])
check("workspace: column types", [x["type"] for x in sales["meta"]["cols"]] == ["text", "number", "date"])
status, st = post("/api/ws/state", {"ws": WS["ws"]})
check("workspace: state survives a page change", status == 200 and len(st["files"]) == 1)

# ---- viewer ----
p = {"ws": sales["ws"], "file": sales["file"], "sheet": sales["sheet"]}
status, q = post("/api/query", {**p, "pivot": {"rows": ["Region"], "cols": [], "values": [{"fn": "sum", "cols": ["Units"]}], "totals": True}})
check("viewer: pivot with grand total row", status == 200 and q["rows"][-1][0] == "Grand total" and q["rows"][-1][-1] == 15)
status, q = post("/api/query", {**p, "search": "south"})
check("viewer: search", status == 200 and q["total"] == 1)
status, _ = post("/api/export", {**p, "fmt": "csv", "scope": "full"})
check("viewer: csv export", status == 200)

# ---- header row, in the workspace so every page benefits ----
titled = upload(xlsx([["Report 2024", ""], ["Name", "Qty"], ["a", 1], ["b", 2]]), "titled.xlsx")
status, h = post("/api/ws/header", {"ws": WS["ws"], "file": titled["file"], "sheet": titled["sheet"], "row": 2})
sheet = next(f for f in h["files"] if f["id"] == titled["file"])["sheets"][0] if status == 200 else {}
check("header row 2 re-detects types", status == 200 and {x["name"]: x["type"] for x in sheet["cols"]} == {"Name": "text", "Qty": "number"})
check("header row 2: the viewer sees the new columns", post("/api/query", {"ws": WS["ws"], "file": titled["file"], "sheet": titled["sheet"]})[1]["columns"] == ["Name", "Qty"])
status, ch = post("/api/tools/chart/data", {"ws": WS["ws"], "file": titled["file"], "sheet": titled["sheet"], "type": "bar", "x": "Name", "ys": ["Qty"], "agg": "sum"})
check("header row 2: the chart maker sees them too", status == 200 and ch["labels"] == ["a", "b"])

# ---- data cleaner on a file that is already open ----
messy = upload(b'Name,Region,Sales,Joined\n alice ,north,"1,200",2024-01-05\nBOB,South,300,2024-02-10\n alice ,north,"1,200",2024-01-05\n,,,\ncarol,,450,\n', "messy.csv")
mp = {"ws": WS["ws"], "file": messy["file"], "sheet": messy["sheet"]}
steps = [{"op": "trim", "cols": [], "collapse": True}, {"op": "empty_rows"}, {"op": "duplicates", "cols": [], "keep": "first"},
         {"op": "case", "cols": ["Name"], "mode": "title"}, {"op": "missing", "cols": ["Region"], "action": "value", "value": "unknown"}]
status, r = post("/api/tools/clean/run", {**mp, "steps": steps})
check("cleaner: duplicates and empty rows removed", status == 200 and r["after"]["rows"] == 3)
check("cleaner: title case and fill", status == 200 and [row[0] for row in r["rows"]] == ["Alice", "Bob", "Carol"] and r["rows"][2][1] == "unknown")
check("cleaner: '1,200' became a number", status == 200 and {x["name"]: x["type"] for x in r["columns"]}["Sales"] == "number")
status, r2 = post("/api/tools/clean/run", {**mp, "steps": [{"op": "convert", "col": "Nope", "to": "number"}]})
check("cleaner: friendly error for a bad column", status == 400 and "Step 1" in r2["error"])
post("/api/tools/clean/run", {**mp, "steps": steps})
for fmt in ("xlsx", "csv"):
    status, body = post("/api/tools/clean/download", {"ws": WS["ws"], "fmt": fmt})
    check(f"cleaner: {fmt} download", status == 200 and len(body) > 20)
status, sv = post("/api/tools/clean/save", {"ws": WS["ws"]})
cleaned = next((f for f in sv["files"] if f["id"] == sv["file"]), None) if status == 200 else None
check("cleaner: cleaned data becomes a file in the workspace", cleaned and cleaned["derived"] and cleaned["sheets"][0]["rows"] == 3)
status, e = post("/api/ws/header", {"ws": WS["ws"], "file": sv["file"], "sheet": 0, "row": 2})
check("cleaned files keep their own header", status == 400)
status, q = post("/api/query", {"ws": WS["ws"], "file": sv["file"], "sheet": 0})
check("viewer can open the cleaned file", status == 200 and q["total"] == 3)

# ---- compare two files from the workspace ----
a = upload(xlsx([["id", "name", "price"], [1, "Pen", 2.5], [2, "Ink", 3], [3, "Pad", 4]]), "a.xlsx")
b = upload(xlsx([["id", "name", "price"], [1, "Pen", 2.5], [2, "Ink", 3.5], [4, "Cap", 1]]), "b.xlsx")
sa, sb = {"file": a["file"], "sheet": a["sheet"]}, {"file": b["file"], "sheet": b["sheet"]}
status, r = post("/api/tools/compare/run", {"ws": WS["ws"], "a": sa, "b": sb, "keys": ["id"]})
s = r["summary"] if status == 200 else {}
check("compare: added / removed / changed / same by key", (s.get("added"), s.get("removed"), s.get("changed"), s.get("same")) == (1, 1, 1, 1))
check("compare: changed cell shows old and new", status == 200 and r["changed"]["rows"][0][-1]["n"] in (3.5, "3.5"))
status, r2 = post("/api/tools/compare/run", {"ws": WS["ws"], "a": sa, "b": sb, "keys": []})
check("compare: by row position", status == 200 and r2["summary"]["changed"] == 2)
status, body = post("/api/tools/compare/download", {"ws": WS["ws"], "fmt": "xlsx", "which": "all"})
check("compare: xlsx report", status == 200 and body[:2] == b"PK")
status, body = post("/api/tools/compare/download", {"ws": WS["ws"], "fmt": "csv", "which": "changed"})
check("compare: csv of changed cells", status == 200 and b"price" in body)

# ---- chart maker ----
chart = upload(b"Region,Sales,Units,Day\nN,10,1,2024-01-03\nS,20,2,2024-01-20\nN,30,3,2024-02-11\nE,5,4,2024-03-01\n", "c.csv")
base = {"ws": WS["ws"], "file": chart["file"], "sheet": chart["sheet"]}
status, r = post("/api/tools/chart/data", {**base, "type": "bar", "x": "Region", "ys": ["Sales"], "agg": "sum", "sort": "value_desc"})
check("chart: bar sums by region, largest first", status == 200 and r["labels"] == ["N", "S", "E"] and r["series"][0]["values"] == [40, 20, 5])
status, r = post("/api/tools/chart/data", {**base, "type": "line", "x": "Day", "ys": ["Sales"], "agg": "sum", "part": "month"})
check("chart: dates grouped by month", status == 200 and r["labels"] == ["2024-01", "2024-02", "2024-03"] and r["series"][0]["values"] == [30, 30, 5])
status, r = post("/api/tools/chart/data", {**base, "type": "bar", "x": "Day", "ys": ["Sales"], "agg": "sum", "part": "month", "group": "Region"})
check("chart: series split by a group column", status == 200 and sorted(x["name"] for x in r["series"]) == ["E", "N", "S"])
status, r = post("/api/tools/chart/data", {**base, "type": "hist", "x": "Sales", "bins": 3})
check("chart: histogram counts every row", status == 200 and sum(r["series"][0]["values"]) == 4)
status, r = post("/api/tools/chart/data", {**base, "type": "scatter", "x": "Units", "ys": ["Sales"]})
check("chart: scatter points", status == 200 and len(r["series"][0]["points"]) == 4)
status, r = post("/api/tools/chart/data", {**base, "type": "pie", "x": "Region", "ys": ["Sales", "Units"], "agg": "sum"})
check("chart: pie rejects several value columns", status == 400)

# ---- housekeeping ----
status, st = post("/api/ws/remove", {"ws": WS["ws"], "file": chart["file"]})
check("workspace: remove a file", status == 200 and all(f["id"] != chart["file"] for f in st["files"]))
print(f"\n{sum(results)} of {len(results)} checks passed")
sys.exit(0 if all(results) else 1)
