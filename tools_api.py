"""API behind the tool pages. Data stays in memory for one hour and is discarded afterwards."""
import functools, math, os, re, tempfile, time, uuid

import duckdb
import polars as pl
from flask import Blueprint, after_this_request, current_app, jsonify, request, send_file

from engine import (cell, chunked, kind_of, q, read_frames, rm, to_duckdb, uniq, write_csv, write_xlsx)

bp = Blueprint("tools", __name__, url_prefix="/api/tools")
TS, TTL, MAX_SESSIONS = {}, 3600, 30
MAX_ROWS = int(os.environ.get("TOOL_MAX_ROWS", 1_000_000))
PREVIEW, MAX_STEPS, MAX_CATS, MAX_GROUPS, MAX_POINTS = 200, 30, 500, 12, 5000
ALLOWED = (".xlsx", ".xlsm", ".xls", ".xlsb", ".ods", ".csv", ".tsv", ".txt")


class UserError(ValueError):
    """A problem the user can fix; the message is shown to them."""


def api(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except UserError as e:
            return jsonify(error=str(e)), 400
        except (duckdb.Error, pl.exceptions.PolarsError) as e:
            return jsonify(error=f"This data could not be processed: {e}"), 400
        except Exception:
            current_app.logger.exception("tool error")
            return jsonify(error="Something went wrong while processing the file. Please try again."), 500
    return wrapper


# ---------- sessions ----------
def _drop(k):
    s = TS.pop(k, None)
    if s and s.get("con"):
        try:
            s["con"].close()
        except Exception:
            pass


def new_session(**kw):
    now = time.time()
    for k in [k for k, v in TS.items() if now - v["t"] > TTL]:
        _drop(k)
    while len(TS) >= MAX_SESSIONS:
        _drop(min(TS, key=lambda k: TS[k]["t"]))
    token = uuid.uuid4().hex
    TS[token] = {"t": now, **kw}
    return token


def session(token):
    s = TS.get(token)
    if not s:
        raise UserError("This session has expired. Upload the file again.")
    s["t"] = time.time()
    return s


def frame(s, sheet):
    d = s.get("frames", {}).get(sheet)
    if d is None:
        raise UserError("Sheet not found. Upload the file again.")
    return d


def body():
    return request.get_json(silent=True) or {}


def cols_info(d):
    return [{"name": c, "type": kind_of(d[c].dtype)} for c in d.columns]


def preview(d, n=PREVIEW):
    return [[cell(v) for v in r] for r in d.head(n).iter_rows()]


def stem(name):
    return re.sub(r"[^\w\- ]+", "_", os.path.splitext(os.path.basename(str(name)))[0]).strip() or "export"


def send_temp(path, filename):
    @after_this_request
    def _cleanup(resp):
        rm(path)
        return resp
    return send_file(path, as_attachment=True, download_name=filename)


def temp(fmt):
    fd, path = tempfile.mkstemp(suffix="." + fmt)
    os.close(fd)
    return path


# ---------- upload / close ----------
@bp.post("/upload")
@api
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        raise UserError("Choose a file first.")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        raise UserError("Unsupported file type. Use xlsx, xls, xlsb, ods, csv, tsv or txt.")
    path = temp(ext.lstrip("."))
    try:
        f.save(path)
        frames = read_frames(path, f.filename)
    except Exception as e:
        raise UserError(f"Could not read this file: {e}")
    finally:
        rm(path)
    if not frames:
        raise UserError("This file has no data.")
    for n, d in frames:
        if d.height > MAX_ROWS:
            raise UserError(f"Sheet '{n}' has {d.height:,} rows. This tool handles up to {MAX_ROWS:,} rows per sheet.")
    token = new_session(frames=dict(frames), name=f.filename)
    return jsonify(token=token, name=f.filename,
                   sheets=[{"name": n, "rows": d.height, "cols": cols_info(d)} for n, d in frames])


@bp.post("/close")
@api
def close():
    t = body().get("token")
    if t in TS:
        _drop(t)
    return jsonify(ok=True)


# =====================================================================================
# Data Cleaner
# =====================================================================================
def pick(df, st, text_only=False, numeric_only=False):
    """Columns a step applies to. An empty selection means all (text or numeric) columns."""
    cols = [c for c in (st.get("cols") or []) if isinstance(c, str)]
    for c in cols:
        if c not in df.columns:
            raise UserError(f"Column not found: {c}")
        if text_only and df[c].dtype != pl.Utf8:
            raise UserError(f"'{c}' is not a text column.")
        if numeric_only and not df[c].dtype.is_numeric():
            raise UserError(f"'{c}' is not a number column.")
    if cols:
        return cols
    if text_only:
        return [c for c in df.columns if df[c].dtype == pl.Utf8]
    if numeric_only:
        return [c for c in df.columns if df[c].dtype.is_numeric()]
    return list(df.columns)


def changed(a, b, cols):
    return sum(int(a[c].ne_missing(b[c]).sum()) for c in cols if c in a.columns and c in b.columns)


def is_blank(df, c):
    return pl.col(c).is_null() | (pl.col(c).str.strip_chars() == "") if df[c].dtype == pl.Utf8 else pl.col(c).is_null()


def op_trim(df, st):
    cols = pick(df, st, text_only=True)
    ex = []
    for c in cols:
        e = pl.col(c).str.strip_chars()
        ex.append((e.str.replace_all(r"\s+", " ") if st.get("collapse") else e).alias(c))
    new = df.with_columns(ex) if ex else df
    return new, f"Trimmed spaces in {len(cols)} text column(s); {changed(df, new, cols):,} cell(s) changed."


def op_empty_rows(df, st):
    new = df.filter(~pl.all_horizontal([is_blank(df, c) for c in df.columns])) if df.width else df
    return new, f"Removed {df.height - new.height:,} empty row(s)."


def op_empty_cols(df, st):
    keep = []
    for c in df.columns:
        s = df[c]
        blank = s.null_count() == s.len() or (s.dtype == pl.Utf8 and bool((s.str.strip_chars().fill_null("") == "").all()))
        if not blank:
            keep.append(c)
    gone = [c for c in df.columns if c not in keep]
    if not keep:
        raise UserError("Every column is empty, so none can be kept.")
    return df.select(keep), (f"Removed {len(gone)} empty column(s): {', '.join(gone[:5])}{'…' if len(gone) > 5 else ''}." if gone else "No empty columns found.")


def op_duplicates(df, st):
    cols = pick(df, st) if st.get("cols") else None
    keep = "last" if st.get("keep") == "last" else "first"
    new = df.unique(subset=cols, keep=keep, maintain_order=True)
    return new, f"Removed {df.height - new.height:,} duplicate row(s) ({'matching on ' + ', '.join(cols) if cols else 'whole row'})."


def title_case(s):
    return " ".join(w[:1].upper() + w[1:].lower() for w in s.split(" "))


def op_case(df, st):
    cols = pick(df, st, text_only=True)
    mode = st.get("mode", "lower")
    if mode not in ("upper", "lower", "title"):
        raise UserError("Choose UPPERCASE, lowercase or Title Case.")
    fn = {"upper": lambda c: pl.col(c).str.to_uppercase(), "lower": lambda c: pl.col(c).str.to_lowercase(),
          "title": lambda c: pl.col(c).map_elements(title_case, return_dtype=pl.Utf8, skip_nulls=True)}[mode]
    new = df.with_columns([fn(c).alias(c) for c in cols]) if cols else df
    return new, f"Changed text case in {len(cols)} column(s); {changed(df, new, cols):,} cell(s) changed."


def parse_value(v, dtype, col):
    try:
        if dtype.is_integer():
            f = float(v)
            if f != int(f):
                raise ValueError
            return int(f)
        if dtype.is_float():
            return float(v)
        if dtype == pl.Boolean:
            if v.strip().lower() not in ("true", "false"):
                raise ValueError
            return v.strip().lower() == "true"
        if dtype.is_temporal():
            from datetime import date
            return date.fromisoformat(v.strip())
    except ValueError:
        raise UserError(f"'{v}' does not fit the {kind_of(dtype)} column '{col}'.")
    return v


def op_missing(df, st):
    action = st.get("action", "drop")
    if action not in ("drop", "value", "mean", "median", "mode", "ffill", "bfill"):
        raise UserError("Choose what to do with missing values.")
    cols = pick(df, st, numeric_only=action in ("mean", "median"))
    blanks = [pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c)).alias(c) for c in cols if df[c].dtype == pl.Utf8]
    d = df.with_columns(blanks) if blanks else df  # blank text counts as missing
    before = sum(d[c].null_count() for c in cols)
    if action == "drop":
        new = d.drop_nulls(subset=cols)
        return new, f"Removed {d.height - new.height:,} row(s) that had missing values."
    ex = []
    for c in cols:
        e, dt = pl.col(c), d[c].dtype
        if action == "value":
            if st.get("value") in (None, ""):
                raise UserError("Type the value to fill in.")
            ex.append(e.fill_null(pl.lit(parse_value(str(st["value"]), dt, c), dtype=dt)).alias(c))
        elif action in ("mean", "median"):
            f = e.cast(pl.Float64)
            ex.append(f.fill_null(f.mean() if action == "mean" else f.median()).alias(c))
        elif action == "mode":
            ex.append(e.fill_null(e.drop_nulls().mode().first()).alias(c))
        else:
            ex.append(e.fill_null(strategy="forward" if action == "ffill" else "backward").alias(c))
    new = d.with_columns(ex)
    return new, f"Filled {before - sum(new[c].null_count() for c in cols):,} missing value(s) in {len(cols)} column(s)."


def op_replace(df, st):
    find, repl = str(st.get("find", "")), str(st.get("replace", ""))
    if not find:
        raise UserError("Type the text to find.")
    cols = pick(df, st, text_only=True)
    ci, whole = not st.get("case"), bool(st.get("whole"))
    ex = []
    for c in cols:
        e = pl.col(c)
        if whole:
            hit = (e.str.to_lowercase() == find.lower()) if ci else (e == find)
            ex.append(pl.when(hit).then(pl.lit(repl)).otherwise(e).alias(c))
        elif ci:
            ex.append(e.str.replace_all("(?i)" + re.escape(find), repl.replace("$", "$$")).alias(c))
        else:
            ex.append(e.str.replace_all(find, repl, literal=True).alias(c))
    new = df.with_columns(ex) if ex else df
    return new, f"Replaced text in {changed(df, new, cols):,} cell(s)."


DATE_FORMATS = {"iso": "%Y-%m-%d", "dmy": "%d/%m/%Y", "mdy": "%m/%d/%Y", "dmy-": "%d-%m-%Y", "ymd/": "%Y/%m/%d"}


def op_convert(df, st):
    c, to = st.get("col"), st.get("to")
    if c not in df.columns:
        raise UserError("Choose a column to convert.")
    s, e = df[c], pl.col(c)
    if to == "text":
        out = e.cast(pl.Utf8)
    elif to == "number":
        out = (e.str.strip_chars().str.replace_all(r"[,\s$€£₹]", "").cast(pl.Float64, strict=False) if s.dtype == pl.Utf8
               else e.cast(pl.Float64, strict=False))
    elif to == "date":
        fmt = DATE_FORMATS.get(st.get("datefmt", "iso"))
        if not fmt:
            raise UserError("Choose a date format.")
        if s.dtype == pl.Utf8:
            out = e.str.strip_chars().str.to_date(fmt, strict=False)
        elif s.dtype.is_temporal():
            out = e.cast(pl.Date)
        else:
            raise UserError(f"'{c}' must be a text or date column to convert to a date.")
    else:
        raise UserError("Choose what to convert to.")
    try:
        new = df.with_columns(out.alias(c))
    except pl.exceptions.PolarsError as ex:
        raise UserError(f"Could not convert '{c}': {ex}")
    failed = new[c].null_count() - s.null_count()
    return new, f"Converted '{c}' to {to}." + (f" {failed:,} value(s) could not be converted and are now empty." if failed > 0 else "")


def op_rename(df, st):
    style = st.get("style", "trim")
    fn = {"trim": lambda n: re.sub(r"\s+", " ", n.strip()),
          "snake": lambda n: re.sub(r"[^0-9a-z]+", "_", n.strip().lower()).strip("_") or "column",
          "lower": lambda n: re.sub(r"\s+", " ", n.strip()).lower(),
          "upper": lambda n: re.sub(r"\s+", " ", n.strip()).upper(),
          "title": lambda n: title_case(re.sub(r"\s+", " ", n.strip()))}.get(style)
    if not fn:
        raise UserError("Choose a naming style.")
    new_names = uniq([fn(c) for c in df.columns])
    m = {a: b for a, b in zip(df.columns, new_names) if a != b}
    return (df.rename(m) if m else df), f"Renamed {len(m)} column(s)."


def op_drop_cols(df, st):
    cols = pick(df, {"cols": st.get("cols")}) if st.get("cols") else []
    if not cols:
        raise UserError("Choose the columns to remove.")
    if len(cols) >= df.width:
        raise UserError("At least one column must remain.")
    return df.drop(cols), f"Removed {len(cols)} column(s)."


CLEAN_OPS = {"trim": ("Trim spaces", op_trim), "empty_rows": ("Remove empty rows", op_empty_rows),
             "empty_cols": ("Remove empty columns", op_empty_cols), "duplicates": ("Remove duplicates", op_duplicates),
             "case": ("Change text case", op_case), "missing": ("Handle missing values", op_missing),
             "replace": ("Find and replace", op_replace), "convert": ("Convert column type", op_convert),
             "rename": ("Clean column names", op_rename), "drop_cols": ("Remove columns", op_drop_cols)}


@bp.post("/clean/run")
@api
def clean_run():
    j = body()
    s = session(j.get("token"))
    df, steps = frame(s, j.get("sheet")), j.get("steps") or []
    if not steps:
        raise UserError("Add at least one cleaning step.")
    if len(steps) > MAX_STEPS:
        raise UserError(f"Use at most {MAX_STEPS} steps.")
    start, log = df, []
    for i, st in enumerate(steps, 1):
        label, fn = CLEAN_OPS.get(st.get("op"), (None, None))
        if not fn:
            raise UserError(f"Step {i} is not a known step.")
        try:
            df, m = fn(df, st)
        except UserError as e:
            raise UserError(f"Step {i} ({label}): {e}")
        except pl.exceptions.PolarsError as e:
            raise UserError(f"Step {i} ({label}) could not be applied: {e}")
        log.append({"step": i, "label": label, "message": m})
    s["clean"] = {"sheet": j.get("sheet"), "df": df}
    return jsonify(before={"rows": start.height, "cols": start.width}, after={"rows": df.height, "cols": df.width},
                   log=log, columns=cols_info(df), rows=preview(df), truncated=df.height > PREVIEW)


@bp.post("/clean/download")
@api
def clean_download():
    j = body()
    s, fmt = session(j.get("token")), j.get("fmt")
    res = s.get("clean")
    if not res:
        raise UserError("Apply the cleaning steps first.")
    if fmt not in ("xlsx", "csv"):
        raise UserError("Unsupported format.")
    d, path = res["df"], temp(fmt)
    if fmt == "csv":
        write_csv(path, d.columns, chunked(d))
    else:
        write_xlsx(path, [(res["sheet"], d.columns, chunked(d))])
    return send_temp(path, f"{stem(s['name'])}_cleaned.{fmt}")


# =====================================================================================
# Compare Files
# =====================================================================================
def lit(s):
    """A SQL string literal."""
    return "'" + str(s).replace("'", "''") + "'"


def compare_side(tag, tbl, df, keys, norm_key):
    cols = ", ".join(f"{q(c)} AS {tag}c{i}" for i, c in enumerate(df.columns))
    ks = "".join(f", {norm_key(k)} AS {tag}k{j}" for j, k in enumerate(keys))
    part = ", ".join(f"{tag}k{j}" for j in range(len(keys))) or "1"
    return (f"SELECT {tag}x.*, ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY {tag}rid) AS {tag}n FROM "
            f"(SELECT __rid AS {tag}rid, {cols}{ks} FROM {tbl}) {tag}x")


@bp.post("/compare/run")
@api
def compare_run():
    j = body()
    ja, jb = j.get("a") or {}, j.get("b") or {}
    A, B = frame(session(ja.get("token")), ja.get("sheet")), frame(session(jb.get("token")), jb.get("sheet"))
    ca, cb = list(A.columns), list(B.columns)
    common = [c for c in ca if c in cb]
    if not common:
        raise UserError("The two sheets share no column names, so they cannot be compared. Check the header rows and column names.")
    keys = [k for k in (j.get("keys") or []) if isinstance(k, str)]
    for k in keys:
        if k not in common:
            raise UserError(f"Key column '{k}' must exist in both files.")
    skip = set(j.get("ignore") or [])
    cmp_cols = [c for c in common if c not in keys and c not in skip]
    if len(cmp_cols) > 200:
        raise UserError("Too many columns to compare (limit 200). Ignore some columns.")
    if not keys and not cmp_cols:
        raise UserError("There is nothing to compare. Keep at least one column.")
    trim, ic = bool(j.get("trim", True)), bool(j.get("ignore_case"))

    def norm(x):  # comparable text: trimmed and/or lower-cased, empty = missing
        e = f"CAST({x} AS VARCHAR)"
        e = f"TRIM({e})" if trim else e
        return f"NULLIF({f'LOWER({e})' if ic else e}, '')"

    numeric = {c: A[c].dtype.is_numeric() and B[c].dtype.is_numeric() for c in common}

    def norm_key(k):
        return f"CAST(CAST({q(k)} AS DOUBLE) AS VARCHAR)" if numeric[k] else norm(q(k))

    def diff(c):
        x, y = f"ac{ca.index(c)}", f"bc{cb.index(c)}"
        if numeric[c]:
            return f"(COALESCE(ABS(CAST({x} AS DOUBLE) - CAST({y} AS DOUBLE)) > 1e-9, FALSE) OR (({x} IS NULL) <> ({y} IS NULL)))"
        return f"({norm(x)} IS DISTINCT FROM {norm(y)})"

    con = duckdb.connect()
    try:
        to_duckdb(con, "a", A.with_row_index("__rid"))
        to_duckdb(con, "b", B.with_row_index("__rid"))
        sa, sb = compare_side("a", "a", A, keys, norm_key), compare_side("b", "b", B, keys, norm_key)
        on = " AND ".join(["x.an = y.bn"] + [f"x.ak{i} IS NOT DISTINCT FROM y.bk{i}" for i in range(len(keys))])
        anyd = " OR ".join(diff(c) for c in cmp_cols) or "FALSE"
        con.execute(f"CREATE TABLE j AS SELECT *, CASE WHEN bn IS NULL THEN 'removed' WHEN an IS NULL THEN 'added' "
                    f"WHEN {anyd} THEN 'changed' ELSE 'same' END AS st FROM (SELECT * FROM ({sa}) x FULL OUTER JOIN ({sb}) y ON {on})")
        counts = dict(con.execute("SELECT st, COUNT(*) FROM j GROUP BY st").fetchall())
        dups = [int(con.execute(f"SELECT COUNT(*) FROM ({s}) WHERE {t}n > 1").fetchone()[0]) for s, t in ((sa, "a"), (sb, "b"))] if keys else [0, 0]
        per_col = {}
        if cmp_cols and counts.get("changed"):
            row = con.execute("SELECT " + ", ".join(f"COUNT(*) FILTER (WHERE st = 'changed' AND {diff(c)})" for c in cmp_cols) + " FROM j").fetchone()
            per_col = {c: int(n) for c, n in zip(cmp_cols, row) if n}
    except Exception:
        con.close()
        raise
    ids = [(k, f"ac{ca.index(k)}") for k in keys] or [("Row", "an")]
    sql = {"added": "SELECT " + ", ".join(f"bc{i} AS {q(c)}" for i, c in enumerate(cb)) + " FROM j WHERE st = 'added' ORDER BY brid",
           "removed": "SELECT " + ", ".join(f"ac{i} AS {q(c)}" for i, c in enumerate(ca)) + " FROM j WHERE st = 'removed' ORDER BY arid"}
    long_parts = [f"SELECT arid AS __o, " + ", ".join(f"{e} AS {q(n)}" for n, e in ids) +
                  f", {lit(c)} AS \"Column\", CAST(ac{ca.index(c)} AS VARCHAR) AS \"Old value\", "
                  f"CAST(bc{cb.index(c)} AS VARCHAR) AS \"New value\" FROM j WHERE st = 'changed' AND {diff(c)}" for c in per_col]
    sql["changed"] = ("SELECT * EXCLUDE (__o) FROM (" + " UNION ALL ".join(long_parts) + ") ORDER BY __o, \"Column\"") if long_parts else None
    wide = ("SELECT " + ", ".join(f"{e} AS i{n}" for n, (_, e) in enumerate(ids)) +
            "".join(f", ac{ca.index(c)} AS o{n}, bc{cb.index(c)} AS n{n}, {diff(c)} AS d{n}" for n, c in enumerate(per_col)) +
            " FROM j WHERE st = 'changed' ORDER BY arid LIMIT 500")
    cur = con.cursor()
    out = {}
    for name in ("added", "removed"):
        r = cur.execute(sql[name] + f" LIMIT 500")
        out[name] = {"columns": [d[0] for d in r.description], "rows": [[cell(v) for v in row] for row in r.fetchall()], "total": counts.get(name, 0)}
    rows = []
    for r in cur.execute(wide).fetchall():
        item = [cell(v) for v in r[:len(ids)]]
        for n in range(len(per_col)):
            o, nw, d = r[len(ids) + n * 3: len(ids) + n * 3 + 3]
            item.append({"o": cell(o), "n": cell(nw)} if d else cell(nw))
        rows.append(item)
    out["changed"] = {"columns": [n for n, _ in ids] + list(per_col), "rows": rows, "total": counts.get("changed", 0)}
    summary = {"rows_a": A.height, "rows_b": B.height, "added": counts.get("added", 0), "removed": counts.get("removed", 0),
               "changed": counts.get("changed", 0), "same": counts.get("same", 0), "mode": "key" if keys else "position",
               "keys": keys, "only_a": [c for c in ca if c not in cb], "only_b": [c for c in cb if c not in ca],
               "dups_a": dups[0], "dups_b": dups[1], "col_diffs": [{"column": c, "count": n} for c, n in per_col.items()]}
    token = new_session(con=con, compare={"sql": sql, "summary": summary}, name=ja.get("name") or "compare")
    return jsonify(token=token, summary=summary, **out)


def qchunks(cur, sql):
    r = cur.execute(sql)
    cols = [d[0] for d in r.description]

    def gen():
        while chunk := r.fetchmany(50_000):
            yield chunk
    return cols, gen()


@bp.post("/compare/download")
@api
def compare_download():
    j = body()
    s, fmt, which = session(j.get("token")), j.get("fmt"), j.get("which", "all")
    c = s.get("compare")
    if not c or fmt not in ("xlsx", "csv") or which not in ("all", "added", "removed", "changed"):
        raise UserError("Run the comparison first.")
    cur, path = s["con"].cursor(), temp(fmt)
    sm = c["summary"]

    def part(name):
        return qchunks(cur, c["sql"][name]) if c["sql"].get(name) else (["Row", "Column", "Old value", "New value"], iter([]))
    if fmt == "csv":
        if which == "all":
            raise UserError("Choose Added, Removed or Changed for a csv download.")
        cols, chunks = part(which)
        write_csv(path, cols, chunks)
        return send_temp(path, f"{stem(s['name'])}_{which}.csv")
    metrics = [("Rows in file A", sm["rows_a"]), ("Rows in file B", sm["rows_b"]),
               ("Matched by", "key: " + ", ".join(sm["keys"]) if sm["keys"] else "row position"),
               ("Added rows (only in B)", sm["added"]), ("Removed rows (only in A)", sm["removed"]),
               ("Changed rows", sm["changed"]), ("Unchanged rows", sm["same"]),
               ("Columns only in A", ", ".join(sm["only_a"]) or "none"), ("Columns only in B", ", ".join(sm["only_b"]) or "none")]
    metrics += [(f"Changed cells in {d['column']}", d["count"]) for d in sm["col_diffs"]]
    sheets = [("Summary", ["Metric", "Value"], [metrics])] + [(n.capitalize(), *part(n)) for n in ("added", "removed", "changed")]
    write_xlsx(path, sheets)
    return send_temp(path, f"{stem(s['name'])}_differences.xlsx")


# =====================================================================================
# Chart Maker
# =====================================================================================
AGGS = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}
PARTS = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}


def finite(v):
    return float(v) if v is not None and math.isfinite(float(v)) else None


def natural(label):
    try:
        return (0, float(label), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(label))


@bp.post("/chart/data")
@api
def chart_data():
    j = body()
    s = session(j.get("token"))
    df, kind = frame(s, j.get("sheet")), j.get("type")
    if kind not in ("bar", "hbar", "line", "area", "pie", "donut", "scatter", "hist"):
        raise UserError("Choose a chart type.")
    types = {c: kind_of(df[c].dtype) for c in df.columns}

    def col(name, what):
        if name not in df.columns:
            raise UserError(f"Choose the {what} column.")
        return name
    con = duckdb.connect()
    try:
        con.register("t", df.to_arrow())
        if kind == "hist":
            x = col(j.get("x"), "number")
            if types[x] != "number":
                raise UserError("A histogram needs a number column.")
            bins = max(2, min(int(j.get("bins") or 20), 100))
            lo, hi = con.execute(f"SELECT MIN({q(x)}), MAX({q(x)}) FROM t WHERE {q(x)} IS NOT NULL").fetchone()
            if lo is None:
                raise UserError(f"'{x}' has no values.")
            w = (float(hi) - float(lo)) / bins or 1.0
            got = dict(con.execute(f"SELECT LEAST(CAST(FLOOR((CAST({q(x)} AS DOUBLE) - {float(lo)}) / {w}) AS INTEGER), {bins - 1}) AS b, COUNT(*) "
                                   f"FROM t WHERE {q(x)} IS NOT NULL GROUP BY 1").fetchall())
            edge = lambda i: f"{float(lo) + w * i:.6g}"
            return jsonify(kind=kind, x_title=x, y_title="Count", labels=[f"{edge(i)} – {edge(i + 1)}" for i in range(bins)],
                           series=[{"name": "Count", "values": [got.get(i, 0) for i in range(bins)]}], total=bins, shown=bins)
        if kind == "scatter":
            x, y = col(j.get("x"), "X"), col(j.get("ys", [None])[0] if j.get("ys") else None, "Y")
            if types[x] != "number" or types[y] != "number":
                raise UserError("A scatter chart needs two number columns.")
            g = j.get("group") or None
            gx = f"COALESCE(NULLIF(CAST({q(col(g, 'group'))} AS VARCHAR), ''), '(Blank)')" if g else "'Points'"
            base = f"FROM t WHERE {q(x)} IS NOT NULL AND {q(y)} IS NOT NULL"
            n = con.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
            samp = f" USING SAMPLE reservoir({MAX_POINTS} ROWS) REPEATABLE (42)" if n > MAX_POINTS else ""
            rows = con.execute(f"SELECT {gx} AS g, CAST({q(x)} AS DOUBLE), CAST({q(y)} AS DOUBLE) FROM t WHERE {q(x)} IS NOT NULL AND {q(y)} IS NOT NULL{samp}").fetchall()
            series = {}
            for gv, a, b in rows:
                series.setdefault(gv, []).append([finite(a), finite(b)])
            if len(series) > MAX_GROUPS:
                raise UserError(f"The group column has more than {MAX_GROUPS} values. Pick one with fewer.")
            return jsonify(kind=kind, x_title=x, y_title=y, series=[{"name": k, "points": v} for k, v in sorted(series.items())], total=n, shown=len(rows))
        # aggregated charts
        x = col(j.get("x"), "category (X)")
        agg, ys = j.get("agg", "sum"), [c for c in (j.get("ys") or []) if c]
        if agg not in AGGS and agg not in ("count", "countd"):
            raise UserError("Choose how to combine values.")
        if agg not in ("count", "countd") and not ys:
            raise UserError("Choose at least one value column, or use Count.")
        for c in ys:
            col(c, "value")
        g = j.get("group") or None
        if g and (len(ys) > 1):
            raise UserError("Use either several value columns or a group column, not both.")
        if kind in ("pie", "donut") and (len(ys) > 1 or g):
            raise UserError("Pie and donut charts use one value column and no group column.")
        part = j.get("part")
        xe = (f"strftime(date_trunc('{part}', {q(x)}), '{PARTS[part]}')" if types[x] == "date" and part in PARTS else
              (f"strftime({q(x)}, '%Y') || '-Q' || CAST(quarter({q(x)}) AS VARCHAR)" if types[x] == "date" and part == "quarter" else f"CAST({q(x)} AS VARCHAR)"))
        xe = f"COALESCE(NULLIF({xe}, ''), '(Blank)')"
        ge = f"COALESCE(NULLIF(CAST({q(g)} AS VARCHAR), ''), '(Blank)')" if g else None
        meas = []
        if agg == "count":
            meas = [("Count", "COUNT(*)")]
        elif agg == "countd":
            meas = [(f"Distinct {c}", f"COUNT(DISTINCT {q(c)})") for c in ys]
        else:
            meas = [(f"{agg} of {c}", f"{AGGS[agg]}({q(c) if types[c] == 'number' else f'TRY_CAST({q(c)} AS DOUBLE)'})") for c in ys]
        sel = f"{xe} AS x" + (f", {ge} AS g" if g else "") + "".join(f", {m} AS m{i}" for i, (_, m) in enumerate(meas))
        rows = con.execute(f"SELECT {sel} FROM t GROUP BY ALL LIMIT 100001").fetchall()
        if len(rows) > 100000:
            raise UserError("The X column has too many distinct values (over 100,000). Pick another column or group dates.")
    finally:
        con.close()
    if g:
        names = sorted({r[1] for r in rows})
        if len(names) > MAX_GROUPS:
            raise UserError(f"The group column has more than {MAX_GROUPS} values. Pick one with fewer.")
        cells = {}
        for r in rows:
            cells.setdefault(r[0], {})[r[1]] = finite(r[2])
        data = {xv: [cells[xv].get(n) for n in names] for xv in cells}
        series_names = names
    else:
        data = {r[0]: [finite(v) for v in r[1:]] for r in rows}
        series_names = [m[0] for m in meas]
    order = j.get("sort", "x")
    total = lambda v: sum(a or 0 for a in v)
    keys = sorted(data, key=natural)
    if order == "value_desc":
        keys.sort(key=lambda k: -total(data[k]))
    elif order == "value_asc":
        keys.sort(key=lambda k: total(data[k]))
    limit = max(1, min(int(j.get("limit") or 30), MAX_CATS))
    shown = keys[:limit]
    return jsonify(kind=kind, x_title=x, y_title=(series_names[0] if len(series_names) == 1 else ""), labels=shown,
                   series=[{"name": n, "values": [data[k][i] for k in shown]} for i, n in enumerate(series_names)],
                   total=len(keys), shown=len(shown))
