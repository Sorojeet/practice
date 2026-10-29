import os, re, tempfile, time, uuid

import duckdb
from flask import Flask, Response, after_this_request, jsonify, redirect, render_template, request, send_file

from engine import cell, file_kind, kind_of, q, read_frames, read_one, rm, to_duckdb, write_csv, write_xlsx
from tools_api import MAX_ROWS, bp as tools_bp
from tools_registry import HOME, SITE, ready_tools

app = Flask(__name__)
ASSET_V = str(int(time.time()))  # changes on every restart, so browsers fetch new CSS/JS after a deploy
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "0"))  # 0 = no limit (set it on small servers)
if MAX_MB:
    app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
app.register_blueprint(tools_bp)


@app.context_processor
def shared():
    return {"tools": ready_tools(), "site": SITE, "v": ASSET_V, "max_mb": MAX_MB, "max_rows": MAX_ROWS,
            "canonical": SITE["url"].rstrip("/") + (request.path if request.path != "/" else "/")}


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"This file is too large. The limit is {MAX_MB} MB."), 413


def _tool_page(tool):
    return lambda: render_template(f"tools/{tool['slug']}.html", page=tool)


for _t in ready_tools():  # one clean URL per finished tool: /tools/<slug>
    app.add_url_rule(f"/tools/{_t['slug']}", endpoint=f"tool_{_t['slug']}", view_func=_tool_page(_t))


@app.get("/tools")
def tools_index():
    return redirect("/#tools", code=301)


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {SITE['url'].rstrip('/')}/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    base = SITE["url"].rstrip("/")
    urls = [("/", "1.0")] + [(f"/tools/{t['slug']}", "0.8") for t in ready_tools()]
    xml = "".join(f"<url><loc>{base}{u}</loc><priority>{pr}</priority></url>" for u, pr in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + xml + "</urlset>",
                    mimetype="application/xml")
SESS, TTL, FULL_MAX, PAGE = {}, 7200, 10_000, 500
AGG = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}
OPS = ("contains", "eq", "ne", "starts", "gt", "gte", "lt", "lte", "empty", "filled")


def drop(k):
    v = SESS.pop(k)
    v["con"].close()
    if v.get("path"):
        try:
            os.remove(v["path"])
        except OSError:
            pass


def register(c, i, d, name, hdr):
    to_duckdb(c, f"t{i}", d)
    return {"id": i, "name": name, "rows": d.height, "hdr": hdr,
            "cols": [{"name": n, "numeric": d[n].dtype.is_numeric(), "type": kind_of(d[n].dtype)} for n in d.columns]}


def load(path, name):
    con = duckdb.connect()
    return con, [register(con, i, d, n, 1) for i, (n, d) in enumerate(read_frames(path, name))], file_kind(name)


def pivot_sql(pv, cols, base, params, con, need):
    """Rows x column fields, one or more totals, with grand-total columns and a grand-total row."""
    prow = list(pv["rows"])
    ccs = [c for c in (pv.get("cols") or []) if c]
    for c in prow + ccs:
        need(c)
    meas, seen = [], set()
    for t in pv.get("values") or [{"fn": "count"}]:
        fn = t.get("fn", "count")
        vcols = [] if fn == "count" else list(t.get("cols") or [])
        if fn != "count" and (fn not in AGG or not vcols):
            raise ValueError("Pick a function and at least one column for each value.")
        for val in vcols or [None]:
            if val is None:
                expr, label = "COUNT(*)", "count"
            else:
                if val not in cols:
                    raise ValueError(f"Unknown column: {val}")
                expr = f"{AGG[fn]}({q(val) if cols[val]['numeric'] else f'TRY_CAST({q(val)} AS DOUBLE)'})"
                label = f"{fn} of {val}"
            if label not in seen:
                seen.add(label)
                meas.append((expr, label))
    multi, totals = len(meas) > 1, pv.get("totals", True)
    ms, mp = [], []
    if ccs:
        exprs = [f"NULLIF(CAST({q(c)} AS VARCHAR), '')" for c in ccs]
        sel = ", ".join(f"{e} AS v{i}" for i, e in enumerate(exprs))
        order = ", ".join(f"(v{i} IS NULL), TRY_CAST(v{i} AS DOUBLE), v{i}" for i in range(len(exprs)))
        combos = con.execute(f"SELECT * FROM (SELECT DISTINCT {sel} {base}) ORDER BY {order} LIMIT 51", params).fetchall()
        if len(combos) > 50:
            raise ValueError("The column fields have more than 50 distinct combinations. Pick fewer or smaller fields.")
        for combo in combos:
            conds = [f"{e} = ?" if v is not None else f"{e} IS NULL" for e, v in zip(exprs, combo)]
            name = " / ".join(v if v is not None else "(Blank)" for v in combo)
            for expr, label in meas:
                ms.append(f"{expr} FILTER (WHERE {' AND '.join(conds)}) AS {q(name + (f' | {label}' if multi else ''))}")
                mp += [v for v in combo if v is not None]
    if totals or not ccs:
        for expr, label in meas:
            ms.append(f"{expr} AS {q(('Grand total' + (f' | {label}' if multi else '')) if ccs else label)}")
    if not ms:
        ms += [f"{expr} AS {q(label)}" for expr, label in meas]
    lab = ", ".join(f"CAST({q(c)} AS VARCHAR) AS {q(c)}" for c in prow)
    tot = ", ".join([f"'Grand total' AS {q(prow[0])}"] + [f"'' AS {q(c)}" for c in prow[1:]])
    a = f"SELECT {lab}, {', '.join(ms)}, 0 AS __t {base} GROUP BY ALL"
    b = f"SELECT {tot}, {', '.join(ms)}, 1 AS __t {base}"
    order = ", ".join(f"TRY_CAST({q(c)} AS DOUBLE), {q(c)}" for c in prow)
    if not totals:
        return f"SELECT * EXCLUDE (__t) FROM ({a}) ORDER BY __t, {order}", mp + params, True, base
    return f"SELECT * EXCLUDE (__t) FROM ({a} UNION ALL {b}) ORDER BY __t, {order}", mp + params + mp + params, True, base


def build(spec, sheet, con=None):
    cols = {c["name"]: c for c in sheet["cols"]}
    params, where = [], []

    def need(c):
        if c not in cols:
            raise ValueError(f"Unknown column: {c}")
        return q(c)

    s = (spec.get("search") or "").strip()
    if s:
        where.append("(" + " OR ".join(f"CAST({q(c)} AS VARCHAR) ILIKE ?" for c in cols) + ")")
        params += [f"%{s}%"] * len(cols)
    parts = []
    for i, f in enumerate(spec.get("filters") or []):
        c, op, v = need(f["col"]), f["op"], str(f.get("value", ""))
        num, txt = cols[f["col"]]["numeric"], f"CAST({q(f['col'])} AS VARCHAR)"
        if op not in OPS:
            raise ValueError("Unknown filter")
        if op == "empty":
            e = f"({c} IS NULL OR {txt} = '')"
        elif op == "filled":
            e = f"({c} IS NOT NULL AND {txt} <> '')"
        elif op in ("contains", "starts"):
            e = f"{txt} ILIKE ?"
            params.append(f"%{v}%" if op == "contains" else f"{v}%")
        elif op in ("gt", "gte", "lt", "lte"):
            e = f"{c if num else txt} {dict(gt='>', gte='>=', lt='<', lte='<=')[op]} ?"
            params.append(float(v) if num else v)
        elif num:
            e = f"{c} {'=' if op == 'eq' else '<>'} ?"
            params.append(float(v))
        else:
            e = f"LOWER({txt}) {'=' if op == 'eq' else '<>'} ?"
            params.append(v.lower())
        j = f.get("join", "AND") if i else ""
        if j not in ("", "AND", "OR"):
            raise ValueError("Unknown join")
        parts.append(f"{j} {e}".strip())
    if parts:
        where.append("(" + " ".join(parts) + ")")
    for pk in spec.get("picks") or []:  # value-list filter (like Excel's checkbox list)
        c = need(pk["col"])
        txt, vals = f"CAST({c} AS VARCHAR)", [str(v) for v in pk.get("values", [])]
        blank = f"({c} IS NULL OR {txt} = '')"
        hit = ([f"COALESCE({txt} IN ({','.join('?' * len(vals))}), FALSE)"] if vals else []) + ([blank] if pk.get("blank") else [])
        params += vals
        if pk.get("mode") == "in":
            where.append("(" + " OR ".join(hit) + ")" if hit else "FALSE")
        elif hit:
            where.append("NOT (" + " OR ".join(hit) + ")")
    base = f"FROM t{sheet['id']}" + (" WHERE " + " AND ".join(where) if where else "")
    pv = spec.get("pivot")
    if pv and pv.get("rows"):  # pivot table
        return pivot_sql(pv, cols, base, params, con, need)
    sort = spec.get("sort") or {}
    sql = f"SELECT * {base}"
    if sort.get("col") in cols:
        sql += f" ORDER BY {q(sort['col'])}" + (" DESC NULLS LAST" if sort.get("dir") == "desc" else " NULLS LAST")
    return sql, params, False, base


def prep(spec):
    s = SESS.get(spec.get("token"))
    if not s:
        raise KeyError("This session has expired. Upload the file again.")
    s["t"] = time.time()
    sheet = next(x for x in s["sheets"] if x["id"] == spec["sheet"])
    return (s, sheet) + build(spec, sheet, s["con"].cursor())


@app.get("/")
def index():
    return render_template("index.html", page=HOME)


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="No file received."), 400
    now = time.time()
    for k in [k for k, v in SESS.items() if now - v["t"] > TTL]:
        drop(k)
    fd, path = tempfile.mkstemp(suffix=os.path.splitext(f.filename)[1])
    os.close(fd)
    try:
        f.save(path)
        con, sheets, kind = load(path, f.filename)
    except Exception as e:
        rm(path)
        return jsonify(error=f"Could not read this file: {e}"), 400
    token = uuid.uuid4().hex
    SESS[token] = {"con": con, "sheets": sheets, "t": now, "path": path, "kind": kind}
    return jsonify(token=token, name=f.filename, sheets=sheets, kind=kind)


@app.post("/api/header")
def header():
    j = request.get_json()
    s = SESS.get(j.get("token"))
    if not s:
        return jsonify(error="This session has expired. Upload the file again."), 400
    try:
        row = int(j.get("row", 1))
        sh = next(x for x in s["sheets"] if x["id"] == j["sheet"])
        if row < 1:
            raise ValueError("Header row must be 1 or higher.")
        d = read_one(s["path"], s["kind"], sh["name"], row)
        if not d.width:
            raise ValueError("No columns found at that row.")
        sh.update(register(s["con"].cursor(), sh["id"], d, sh["name"], row))
    except Exception as e:
        return jsonify(error=f"Could not use row {j.get('row')} as the header: {e}"), 400
    return jsonify(sheet=sh)


@app.post("/api/close")
def close():
    t = (request.get_json(silent=True) or {}).get("token")
    if t in SESS:
        drop(t)
    return jsonify(ok=True)


@app.post("/api/values")
def values():
    spec = request.get_json()
    col, qs = spec.get("col"), (spec.get("q") or "").strip()
    spec = {**spec, "pivot": None, "sort": None, "picks": [x for x in spec.get("picks") or [] if x["col"] != col]}
    try:
        s, sheet, _, params, _, base = prep(spec)
        if col not in [x["name"] for x in sheet["cols"]]:
            raise ValueError("Unknown column.")
        txt, extra = f"CAST({q(col)} AS VARCHAR)", ""
        if qs:
            extra = (" AND " if " WHERE " in base else " WHERE ") + f"{txt} ILIKE ?"
            params = params + [f"%{qs}%"]
        rows = s["con"].cursor().execute(
            f"SELECT v, n FROM (SELECT NULLIF({txt}, '') AS v, COUNT(*) AS n {base}{extra} GROUP BY 1) "
            "ORDER BY (v IS NULL), TRY_CAST(v AS DOUBLE), v LIMIT 1001", params).fetchall()
    except (ValueError, KeyError, StopIteration, duckdb.Error) as e:
        return jsonify(error=str(e)), 400
    return jsonify(values=[[v, n] for v, n in rows[:1000]], truncated=len(rows) > 1000)


@app.post("/api/query")
def query():
    spec = request.get_json()
    try:
        s, sheet, sql, params, grouped, base = prep(spec)
        cur = s["con"].cursor()
        total = cur.execute(f"SELECT COUNT(*) FROM ({sql})" if grouped else f"SELECT COUNT(*) {base}", params).fetchone()[0]
        full = grouped or total <= FULL_MAX
        size = min(total, 200_000) if full else PAGE
        page = 1 if full else max(int(spec.get("page", 1)), 1)
        r = cur.execute(f"{sql} LIMIT {size} OFFSET {(page - 1) * size}", params)
        cols = [d[0] for d in r.description]
        rows = [[cell(v) for v in row] for row in r.fetchall()]
    except (ValueError, KeyError, StopIteration, duckdb.Error) as e:
        return jsonify(error=str(e)), 400
    return jsonify(columns=cols, rows=rows, total=total, page=page,
                   pages=1 if full else -(-total // PAGE), grouped=grouped)


@app.post("/api/export")
def export():
    spec = request.get_json()
    fmt = spec.get("fmt")
    if spec.get("scope") == "full":
        spec = {"token": spec.get("token"), "sheet": spec.get("sheet")}
    try:
        s, sheet, sql, params, grouped, _ = prep(spec)
        if fmt not in ("xlsx", "csv", "pdf"):
            raise ValueError("Unsupported format.")
        if fmt == "pdf" and not grouped:
            raise ValueError("PDF export is available for pivot tables only.")
        r = s["con"].cursor().execute(sql, params)
    except (ValueError, KeyError, StopIteration, duckdb.Error) as e:
        return jsonify(error=str(e)), 400
    cols = [d[0] for d in r.description]
    name = re.sub(r'[\[\]:*?/\\]', "_", sheet["name"]) or "export"
    fd, path = tempfile.mkstemp(suffix="." + fmt)
    os.close(fd)
    def chunks():
        while chunk := r.fetchmany(50_000):
            yield chunk

    if fmt == "csv":
        write_csv(path, cols, chunks())
    elif fmt == "xlsx":
        write_xlsx(path, [(name, cols, chunks())])
    else:
        from xml.sax.saxutils import escape
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape, portrait
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

        def fmtv(v):
            if isinstance(v, float):
                return f"{v:,.2f}"
            return f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v)

        raw = r.fetchmany(5001)
        more, rows = len(raw) > 5000, [[cell(v) for v in row] for row in raw[:5000]]
        n = len(cols)
        num = [any(isinstance(x[j], (int, float)) for x in rows) and all(isinstance(x[j], (int, float)) or x[j] == "" for x in rows) for j in range(n)]
        data = [[s if len(s) <= 40 else s[:39] + "…" for s in (fmtv(v) if v != "" else "" for v in row)] for row in rows]
        green, margin = colors.HexColor("#1f9d5c"), 24
        ps = portrait(A4) if n <= 6 else landscape(A4)
        avail, fs = ps[0] - 2 * margin, 10

        def natural(size):  # column widths that fit their content
            return [max([min(stringWidth(str(h), "Helvetica-Bold", size), 120)] + [stringWidth(x[j], "Helvetica", size) for x in data]) + 14
                    for j, h in enumerate(cols)]
        while True:  # largest font that fits the page, then stretch the table to the full width
            w = natural(fs)
            if sum(w) <= avail or fs <= 6:
                break
            fs -= 1
        w = [x * avail / sum(w) for x in w]
        head = [Paragraph(escape(str(c)), ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=fs, leading=fs + 2,
                          textColor=colors.white, alignment=2 if num[j] else 0)) for j, c in enumerate(cols)]
        t = Table([head] + data, colWidths=w, repeatRows=1, hAlign="LEFT")
        st = [("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), fs), ("LEADING", (0, 0), (-1, -1), fs + 3),
              ("BACKGROUND", (0, 0), (-1, 0), green), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#9bb8a8")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef8f1")])]
        st += [("ALIGN", (j, 1), (j, -1), "RIGHT") for j in range(n) if num[j]]
        st += [("FONTNAME", (j, 1), (j, -1), "Helvetica-Bold") for j, c in enumerate(cols) if c.startswith("Grand total")]
        for i, row in enumerate(data, 1):  # bold grand total row
            if row and row[0] == "Grand total":
                st += [("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"), ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#cfeadb")),
                       ("LINEABOVE", (0, i), (-1, i), 1, green)]
        t.setStyle(st)
        story = [Paragraph(escape(f"{name}: pivot table"), ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceAfter=6))]
        if more:
            story.append(Paragraph("Showing the first 5,000 rows.", ParagraphStyle("n", fontName="Helvetica", fontSize=8, textColor=colors.grey, spaceAfter=4)))
        SimpleDocTemplate(path, pagesize=ps, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin).build(story + [t])

    @after_this_request
    def rm(resp):
        try:
            os.remove(path)
        except OSError:
            pass
        return resp

    return send_file(path, as_attachment=True, download_name=f"{name}.{fmt}")


if __name__ == "__main__":
    app.run(threaded=True)
