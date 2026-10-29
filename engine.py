"""Shared helpers used by the viewer and every tool: file reading, type detection, safe SQL names, exports."""
import csv, math, os, re
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal

import duckdb
import polars as pl

BIG = 10 ** 10
EXCEL = (".xlsx", ".xlsm", ".xls", ".xlsb", ".ods")
TEXT_EXT = (".csv", ".tsv", ".txt")
NUM = r"^-?(\d+|\d{1,3}(,\d{3})+)(\.\d+)?$"  # 12, -3.5, 1,234.50


def q(n):
    """Quote an identifier for SQL."""
    return '"' + str(n).replace('"', '""') + '"'


def rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def cell(v):
    """Make a Python value safe for JSON, csv and xlsx."""
    if v is None:
        return ""
    if isinstance(v, float):
        return v if math.isfinite(v) else ""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, (timedelta, dtime)):
        return str(v)
    return float(v) if isinstance(v, Decimal) else v


# ---------- type detection ----------
def infer_text(s):
    """Turn a text column into numbers, booleans or dates when every value fits. IDs with more than 10 digits
    or leading zeros stay text (the 10-digit rule applies to the whole-number part only)."""
    t = s.to_frame("x").select(pl.when(pl.col("x").str.strip_chars() == "").then(None)
                               .otherwise(pl.col("x").str.strip_chars()).alias("x"))["x"]
    v = t.drop_nulls()
    if not v.len():
        return t
    if v.str.contains(NUM).all():
        u = t.str.replace_all(",", "")
        w = u.drop_nulls()
        if w.str.contains(r"^-?0\d|^-?\d{11,}").any():
            return t
        return u.cast(pl.Int64 if w.str.contains(r"^-?\d+$").all() else pl.Float64)
    if v.str.to_lowercase().is_in(["true", "false"]).all():
        return t.str.to_lowercase() == "true"
    if v.str.contains(r"^\d{4}-\d{2}-\d{2}$").all():
        d = t.str.to_date("%Y-%m-%d", strict=False)
        if d.null_count() == t.null_count():
            return d
    if v.str.contains(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$").all():
        d = t.str.replace("T", " ").str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False)
        if d.null_count() == t.null_count():
            return d
    return t


def detect_types(df, infer=True):
    """Detect column types for every source (CSV and Excel)."""
    out = []
    for c in df.columns:
        s = df[c]
        if infer and s.dtype == pl.Utf8:
            s = infer_text(s)
        elif s.dtype.is_integer() and s.len() and (s.abs().max() or 0) >= BIG:
            s = s.cast(pl.Utf8)
        elif s.dtype.is_float() and s.len() and (s.abs().max() or 0) >= BIG:
            s = s.map_elements(lambda x: str(int(x)) if float(x).is_integer() else repr(x),
                               return_dtype=pl.Utf8, skip_nulls=True)
        out.append(s.alias(c))
    return pl.DataFrame(out)


def kind_of(dt):
    return "number" if dt.is_numeric() else "date" if dt.is_temporal() else "bool" if dt == pl.Boolean else "text"


def uniq(names):
    seen, out = {}, []
    for i, n in enumerate(names):
        n = str(n).strip() if n is not None and str(n).strip() else f"column_{i + 1}"
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    return out


# ---------- reading ----------
def file_kind(name):
    return "xlsx" if os.path.splitext(name)[1].lower() in EXCEL else "csv"


def read_one(path, kind, sheet_name, hdr):
    """Read one sheet, using row `hdr` (1-based) as the header and skipping the rows above it."""
    if kind == "csv":  # delimiter is auto-detected by DuckDB's sniffer
        return detect_types(duckdb.read_csv(path, all_varchar=True, sample_size=-1, skiprows=hdr - 1, header=True).pl())
    try:
        return detect_types(pl.read_excel(path, sheet_name=sheet_name, engine="calamine",
                                          read_options={"header_row": hdr - 1}, infer_schema_length=None))
    except Exception:  # fallback: read raw, then promote the chosen row to the header
        raw = pl.read_excel(path, sheet_name=sheet_name, engine="openpyxl", has_header=False, infer_schema_length=None)
        names = uniq(raw.row(hdr - 1))
        return detect_types(raw.slice(hdr).rename(dict(zip(raw.columns, names))))


def read_frames(path, name):
    """All non-empty sheets of a file as [(sheet name, typed DataFrame)], header on row 1."""
    if file_kind(name) == "xlsx":
        try:
            book = pl.read_excel(path, sheet_id=0, engine="calamine", infer_schema_length=None)
        except ImportError:
            book = pl.read_excel(path, sheet_id=0, engine="openpyxl", infer_schema_length=None)
        frames = [(n, detect_types(d)) for n, d in book.items()]
    else:
        frames = [(os.path.splitext(os.path.basename(name))[0], read_one(path, "csv", None, 1))]
    return [(n, d) for n, d in frames if d.width]


def to_duckdb(con, table, df):
    con.execute(f"DROP TABLE IF EXISTS {q(table)}")
    con.register("__v", df.to_arrow())
    con.execute(f"CREATE TABLE {q(table)} AS SELECT * FROM __v")
    con.unregister("__v")


# ---------- writing ----------
def write_csv(path, cols, chunks):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for chunk in chunks:
            w.writerows([[cell(v) for v in row] for row in chunk])


def write_xlsx(path, sheets, limit=1_048_575):
    """sheets: [(name, columns, iterable of row-chunks)]. Text is always written as text, never as a formula."""
    import xlsxwriter
    wb = xlsxwriter.Workbook(path, {"constant_memory": True, "nan_inf_to_errors": True})
    head, used = wb.add_format({"bold": True, "bg_color": "#1f9d5c", "font_color": "#ffffff"}), set()
    for name, cols, chunks in sheets:
        n, k = (re.sub(r'[\[\]:*?/\\]', "_", str(name))[:31] or "Sheet"), 2
        base = n
        while n.lower() in used:
            suffix = f" ({k})"
            n, k = base[:31 - len(suffix)] + suffix, k + 1
        used.add(n.lower())
        ws, i = wb.add_worksheet(n), 1
        for j, c in enumerate(cols):
            ws.write_string(0, j, str(c), head)
        for chunk in chunks:
            for row in chunk:
                if i > limit:
                    break
                for j, v in enumerate(map(cell, row)):
                    if isinstance(v, str):
                        ws.write_string(i, j, v)
                    else:
                        ws.write(i, j, v)
                i += 1
    wb.close()


def chunked(df, size=50_000):
    """Row chunks of a Polars DataFrame, for write_csv / write_xlsx."""
    for off in range(0, df.height, size):
        yield df.slice(off, size).rows()
