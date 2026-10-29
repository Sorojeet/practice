"""End-to-end check of the viewer and the three tools using the real libraries.
Run from the project folder:  python scripts/smoke_test.py      (optional: pip install openpyxl to inspect the xlsx downloads)"""
import io, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xlsxwriter
from app import app

c, results = app.test_client(), []


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


def up(url, data, name):
    r = c.post(url, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    return r.status_code, r.get_json()


def tool_upload(data, name):
    status, j = up("/api/tools/upload", data, name)
    assert status == 200, j
    return j


def post(url, body):
    r = c.post(url, json=body)
    return r.status_code, (r.get_json() if r.is_json else r.data)


# ---- pages ----
for path in ("/", "/tools/data-cleaner", "/tools/compare-files", "/tools/chart-maker", "/sitemap.xml", "/robots.txt", "/healthz"):
    check(f"GET {path}", c.get(path).status_code == 200)

# ---- viewer: csv, header row 2 ----
csv_bytes = b"Region;Units;Day\nNorth;5;2024-01-05\nSouth;7;2024-02-05\nNorth;3;2024-03-05\n"
status, j = up("/api/upload", csv_bytes, "sales.csv")
check("viewer: semicolon csv is detected", status == 200 and [x["name"] for x in j["sheets"][0]["cols"]] == ["Region", "Units", "Day"])
check("viewer: column types", [x["type"] for x in j["sheets"][0]["cols"]] == ["text", "number", "date"])
status, q = post("/api/query", {"token": j["token"], "sheet": 0, "pivot": {"rows": ["Region"], "cols": [], "values": [{"fn": "sum", "cols": ["Units"]}], "totals": True}})
check("viewer: pivot with grand total row", status == 200 and q["rows"][-1][0] == "Grand total" and q["rows"][-1][-1] == 15)
status, _ = post("/api/export", {"token": j["token"], "sheet": 0, "fmt": "csv", "scope": "full"})
check("viewer: csv export", status == 200)
status, j = up("/api/upload", xlsx([["Report 2024", ""], ["Name", "Qty"], ["a", 1], ["b", 2]]), "titled.xlsx")
status, h = post("/api/header", {"token": j["token"], "sheet": 0, "row": 2})
check("viewer: header row 2 re-detects types", status == 200 and {x["name"]: x["type"] for x in h["sheet"]["cols"]} == {"Name": "text", "Qty": "number"})

# ---- data cleaner ----
messy = b'Name,Region,Sales,Joined\n alice ,north,"1,200",2024-01-05\nBOB,South,300,2024-02-10\n alice ,north,"1,200",2024-01-05\n,,,\ncarol,,450,\n'
u = tool_upload(messy, "messy.csv")
steps = [{"op": "trim", "cols": [], "collapse": True}, {"op": "empty_rows"}, {"op": "duplicates", "cols": [], "keep": "first"},
         {"op": "case", "cols": ["Name"], "mode": "title"}, {"op": "missing", "cols": ["Region"], "action": "value", "value": "unknown"}]
status, r = post("/api/tools/clean/run", {"token": u["token"], "sheet": u["sheets"][0]["name"], "steps": steps})
check("cleaner: duplicates and empty rows removed", status == 200 and r["after"]["rows"] == 3)
check("cleaner: title case and fill", status == 200 and [row[0] for row in r["rows"]] == ["Alice", "Bob", "Carol"] and r["rows"][2][1] == "unknown")
check("cleaner: '1,200' became a number", status == 200 and {c_["name"]: c_["type"] for c_ in r["columns"]}["Sales"] == "number")
status, r = post("/api/tools/clean/run", {"token": u["token"], "sheet": u["sheets"][0]["name"], "steps": [{"op": "convert", "col": "Nope", "to": "number"}]})
check("cleaner: friendly error for a bad column", status == 400 and "Step 1" in r["error"])
for fmt in ("xlsx", "csv"):
    status, body = post("/api/tools/clean/download", {"token": u["token"], "fmt": fmt})
    check(f"cleaner: {fmt} download", status == 200 and len(body) > 20)

# ---- compare files ----
a = tool_upload(xlsx([["id", "name", "price"], [1, "Pen", 2.5], [2, "Ink", 3], [3, "Pad", 4]]), "a.xlsx")
b = tool_upload(xlsx([["id", "name", "price"], [1, "Pen", 2.5], [2, "Ink", 3.5], [4, "Cap", 1]]), "b.xlsx")
sa, sb = {"token": a["token"], "sheet": a["sheets"][0]["name"], "name": "a.xlsx"}, {"token": b["token"], "sheet": b["sheets"][0]["name"], "name": "b.xlsx"}
status, r = post("/api/tools/compare/run", {"a": sa, "b": sb, "keys": ["id"]})
s = r["summary"] if status == 200 else {}
check("compare: added / removed / changed / same by key", (s.get("added"), s.get("removed"), s.get("changed"), s.get("same")) == (1, 1, 1, 1))
check("compare: changed cell shows old and new", status == 200 and r["changed"]["rows"][0][-1] == {"o": 3.0, "n": 3.5} or status == 200 and r["changed"]["rows"][0][-1] in ({"o": 3, "n": 3.5}, {"o": "3.0", "n": "3.5"}))
status, r2 = post("/api/tools/compare/run", {"a": sa, "b": sb, "keys": []})
check("compare: by row position", status == 200 and r2["summary"]["changed"] == 2)
status, body = post("/api/tools/compare/download", {"token": r["token"], "fmt": "xlsx", "which": "all"})
check("compare: xlsx report", status == 200 and body[:2] == b"PK")
status, body = post("/api/tools/compare/download", {"token": r["token"], "fmt": "csv", "which": "added"})
check("compare: csv of added rows", status == 200 and b"Cap" in body)

# ---- chart maker ----
ch = tool_upload(b"Region,Sales,Units,Day\nN,10,1,2024-01-03\nS,20,2,2024-01-20\nN,30,3,2024-02-11\nE,5,4,2024-03-01\n", "c.csv")
base = {"token": ch["token"], "sheet": ch["sheets"][0]["name"]}
status, r = post("/api/tools/chart/data", {**base, "type": "bar", "x": "Region", "ys": ["Sales"], "agg": "sum", "sort": "value_desc"})
check("chart: bar sums by region, largest first", status == 200 and r["labels"] == ["N", "S", "E"] and r["series"][0]["values"] == [40, 20, 5])
status, r = post("/api/tools/chart/data", {**base, "type": "line", "x": "Day", "ys": ["Sales"], "agg": "sum", "part": "month"})
check("chart: dates grouped by month", status == 200 and r["labels"] == ["2024-01", "2024-02", "2024-03"] and r["series"][0]["values"] == [30, 30, 5])
status, r = post("/api/tools/chart/data", {**base, "type": "bar", "x": "Day", "ys": ["Sales"], "agg": "sum", "part": "month", "group": "Region"})
check("chart: series split by a group column", status == 200 and sorted(s_["name"] for s_ in r["series"]) == ["E", "N", "S"])
status, r = post("/api/tools/chart/data", {**base, "type": "hist", "x": "Sales", "bins": 3})
check("chart: histogram counts every row", status == 200 and sum(r["series"][0]["values"]) == 4)
status, r = post("/api/tools/chart/data", {**base, "type": "scatter", "x": "Units", "ys": ["Sales"]})
check("chart: scatter points", status == 200 and len(r["series"][0]["points"]) == 4)
status, r = post("/api/tools/chart/data", {**base, "type": "pie", "x": "Region", "ys": ["Sales", "Units"], "agg": "sum"})
check("chart: pie rejects several value columns", status == 400)

print(f"\n{sum(results)} of {len(results)} checks passed")
sys.exit(0 if all(results) else 1)
