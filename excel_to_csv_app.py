import csv
import html
import io
import re
import zipfile
from pathlib import Path

import polars as pl
import streamlit as st
from xlsxwriter import Workbook

st.set_page_config(
    page_title="Excel ⇄ CSV Converter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------------------------
# Styling (works in both light and dark themes)
# ----------------------------------------------------------------------------
CSS = """
<style>
.block-container { padding-top: 2rem; max-width: 1200px; }
#MainMenu, footer { visibility: hidden; }

/* Hero banner */
.hero {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #db2777 100%);
    border-radius: 20px;
    padding: 2.2rem 2.5rem;
    color: #fff;
    margin-bottom: 1.6rem;
    box-shadow: 0 10px 30px rgba(124, 58, 237, 0.30);
}
.hero h1 { margin: 0; font-size: 2.2rem; font-weight: 800; color: #fff; padding: 0; }
.hero p  { margin: .4rem 0 0 0; font-size: 1.05rem; opacity: .92; color: #fff; }

/* Generic cards */
.card {
    background: rgba(128, 128, 128, 0.07);
    border: 1px solid rgba(128, 128, 128, 0.20);
    border-radius: 16px;
    padding: 1.2rem 1.3rem;
    height: 100%;
}
.card .icon  { font-size: 1.8rem; }
.card .title { font-weight: 700; font-size: 1.05rem; margin-top: .3rem; }
.card .desc  { opacity: .75; font-size: .92rem; margin-top: .15rem; }

/* Sheet selector (radio styled as chips) */
div[role="radiogroup"] { gap: .6rem; flex-wrap: wrap; }
div[role="radiogroup"] > label {
    background: rgba(128, 128, 128, 0.07);
    border: 1px solid rgba(128, 128, 128, 0.30);
    border-radius: 12px;
    padding: .55rem 1rem;
    cursor: pointer;
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
}
div[role="radiogroup"] > label:hover {
    transform: translateY(-2px);
    border-color: #7c3aed;
    box-shadow: 0 6px 16px rgba(0,0,0,.12);
}
div[role="radiogroup"] > label:has(input:checked) {
    background: rgba(124, 58, 237, 0.16);
    border: 2px solid #7c3aed;
    font-weight: 700;
}

/* Metrics */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(79,70,229,.12), rgba(219,39,119,.10));
    border: 1px solid rgba(128, 128, 128, 0.20);
    border-radius: 16px;
    padding: 1rem 1.2rem;
}
[data-testid="stMetricLabel"] { opacity: .8; }
[data-testid="stMetricValue"] { font-weight: 800; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: .4rem; }
.stTabs [data-baseweb="tab"] {
    border-radius: 10px 10px 0 0;
    padding: .6rem 1.2rem;
    font-weight: 600;
}

/* Buttons */
.stDownloadButton button, .stButton button {
    border-radius: 12px;
    padding: .65rem 1.4rem;
    font-weight: 700;
    border: none;
    color: #fff;
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    box-shadow: 0 4px 14px rgba(124, 58, 237, .35);
    transition: transform .15s ease, box-shadow .15s ease;
}
.stDownloadButton button:hover, .stButton button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(124, 58, 237, .45);
    color: #fff;
}

/* Uploader */
[data-testid="stFileUploader"] section {
    border: 2px dashed rgba(124, 58, 237, .55);
    border-radius: 16px;
    background: rgba(124, 58, 237, .05);
}

/* Dataframes */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid rgba(128,128,128,.2); }

/* Filename pill */
.file-pill {
    display: inline-block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: rgba(124, 58, 237, .14);
    border: 1px solid rgba(124, 58, 237, .45);
    border-radius: 999px;
    padding: .35rem 1rem;
    font-weight: 600;
}

/* ---------- Shadow effects ---------- */
.hero {
    box-shadow: 0 20px 40px -12px rgba(124, 58, 237, .45),
                0 8px 16px -8px rgba(0, 0, 0, .25);
}
.card {
    box-shadow: 0 4px 6px rgba(0,0,0,.06), 0 10px 24px rgba(0,0,0,.10);
    transition: transform .2s ease, box-shadow .2s ease;
}
.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 14px 30px rgba(124, 58, 237, .25), 0 6px 12px rgba(0,0,0,.12);
}
[data-testid="stMetric"] {
    box-shadow: 0 4px 6px rgba(0,0,0,.06), 0 8px 20px rgba(79, 70, 229, .15);
    transition: transform .2s ease, box-shadow .2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 26px rgba(79, 70, 229, .28);
}
[data-testid="stDataFrame"] {
    box-shadow: 0 6px 20px rgba(0,0,0,.14);
}
[data-testid="stFileUploader"] section {
    box-shadow: 0 6px 18px rgba(124, 58, 237, .18);
    transition: box-shadow .2s ease, transform .2s ease;
}
[data-testid="stFileUploader"] section:hover {
    box-shadow: 0 10px 28px rgba(124, 58, 237, .32);
    transform: translateY(-2px);
}
div[role="radiogroup"] > label {
    box-shadow: 0 2px 8px rgba(0,0,0,.10);
}
div[role="radiogroup"] > label:has(input:checked) {
    box-shadow: 0 6px 18px rgba(124, 58, 237, .40);
}
[data-testid="stExpander"] details {
    border-radius: 14px;
    box-shadow: 0 4px 14px rgba(0,0,0,.10);
}
[data-baseweb="select"] > div, [data-baseweb="input"] {
    box-shadow: 0 2px 8px rgba(0,0,0,.10);
    border-radius: 10px;
}
[data-testid="stSidebar"] {
    box-shadow: 4px 0 24px rgba(0,0,0,.14);
}
.file-pill {
    box-shadow: 0 4px 12px rgba(124, 58, 237, .25);
}
.stTabs [aria-selected="true"] {
    text-shadow: 0 1px 8px rgba(124, 58, 237, .35);
}

/* ---------- Sidebar content ---------- */
.sb-brand {
    font-size: 1.35rem; font-weight: 800; line-height: 1.2;
    background: linear-gradient(135deg, #4f46e5, #db2777);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    margin-bottom: .1rem;
}
.sb-sub { opacity: .7; font-size: .85rem; margin-bottom: .6rem; }
.sb-heading { font-weight: 700; font-size: 1rem; margin: .9rem 0 .35rem 0; }
.sb-group { font-weight: 600; font-size: .85rem; opacity: .85; margin: .7rem 0 .2rem 0; }
.sb-step { display: flex; gap: .65rem; align-items: flex-start; margin: .42rem 0; }
.sb-num {
    flex: 0 0 24px; height: 24px; border-radius: 50%;
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: #fff; font-weight: 700; font-size: .78rem;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 3px 8px rgba(124, 58, 237, .40);
}
.sb-txt { font-size: .88rem; line-height: 1.35; padding-top: 2px; }
.sb-tip {
    background: rgba(124, 58, 237, .10);
    border: 1px solid rgba(124, 58, 237, .30);
    border-radius: 12px; padding: .7rem .85rem; font-size: .84rem; line-height: 1.4;
    box-shadow: 0 4px 12px rgba(124, 58, 237, .12);
    margin: .3rem 0;
}
.sb-foot { opacity: .6; font-size: .78rem; text-align: center; margin-top: 1rem; }

/* ---------- Column name chips ---------- */
.col-chips { display: flex; flex-wrap: wrap; gap: .5rem; margin: .3rem 0 .2rem 0; }
.col-chip {
    background: rgba(124, 58, 237, .12);
    border: 1px solid rgba(124, 58, 237, .35);
    border-radius: 999px;
    padding: .25rem .8rem;
    font-size: .86rem;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(124, 58, 237, .15);
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


PREVIEW_ROWS = 10  # CSV -> Excel preview: first rows of each file
EXCEL_PREVIEW_MAX = 100_000  # Excel -> CSV preview shows all rows up to this cap


# ----------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------
def show_df(data, **kwargs):
    """st.dataframe that works on both old and new Streamlit versions."""
    try:
        st.dataframe(data, width="stretch", **kwargs)
    except Exception:
        st.dataframe(data, use_container_width=True, **kwargs)


def safe_name(text: str) -> str:
    return re.sub(r'[\\/*?:"<>|]+', "_", text).strip()


def human_size(n: int) -> str:
    size = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def empty_state(cards):
    cols = st.columns(len(cards))
    for col, (icon, title, desc) in zip(cols, cards):
        col.markdown(
            f'<div class="card"><div class="icon">{icon}</div>'
            f'<div class="title">{title}</div><div class="desc">{desc}</div></div>',
            unsafe_allow_html=True,
        )


# ----------------------------------------------------------------------------
# Excel -> CSV helpers
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="Reading Excel file...")
def load_all_sheets(file_bytes: bytes) -> dict[str, pl.DataFrame]:
    """Load every sheet in the workbook as {sheet_name: DataFrame}."""
    return pl.read_excel(
        io.BytesIO(file_bytes),
        sheet_id=0,  # 0 = read ALL sheets
        infer_schema_length=None,  # scan all rows to avoid mixed-type errors
    )


def to_csv_bytes(df: pl.DataFrame, sep: str, header: bool) -> bytes:
    return df.write_csv(separator=sep, include_header=header).encode("utf-8")


# ----------------------------------------------------------------------------
# CSV -> Excel helpers
# ----------------------------------------------------------------------------
DELIMITERS = {
    "Auto-detect": None,
    "Comma ( , )": ",",
    "Semicolon ( ; )": ";",
    "Tab": "\t",
    "Pipe ( | )": "|",
}


def detect_delimiter(file_bytes: bytes) -> str:
    sample = file_bytes[:8192].decode("utf-8", errors="ignore")
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:
        return ","


# Polars can raise PanicException (not a subclass of Exception) on rare failures
try:
    from polars.exceptions import PanicException
except Exception:  # pragma: no cover
    PanicException = Exception
CATCH = (Exception, PanicException)

_INT_RE = r"^[+-]?\d+$"
_FLOAT_RE = r"^[+-]?(\d+\.\d*|\.\d+|\d+)$"
_LEADING_ZERO_RE = r"^[+-]?0\d"
_DATE_FORMATS = ["%Y-%m-%d"]
_DATETIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]
_MAX_SAFE_DIGITS = 15  # Excel stores at most 15 significant digits


def _convert_column(s: pl.Series) -> pl.Series:
    """Convert one text column to int / float / date / datetime when it is safe.

    Columns are left as text when conversion could change the data: leading zeros
    (e.g. 00123), more than 15 digits (Excel would round them), mixed content,
    or ambiguous date formats. Any problem keeps the original text column.
    """
    try:
        if s.dtype != pl.String:
            return s

        t = s.str.strip_chars()
        clean = t.zip_with(t != "", pl.Series(values=[None] * t.len(), dtype=pl.String))
        vals = clean.drop_nulls()
        if vals.len() == 0:
            return s

        no_leading_zero = not vals.str.contains(_LEADING_ZERO_RE).any()
        digits_ok = vals.str.count_matches(r"\d").max() <= _MAX_SAFE_DIGITS

        if no_leading_zero and digits_ok:
            if vals.str.contains(_INT_RE).all():
                return clean.cast(pl.Int64)
            if vals.str.contains(_FLOAT_RE).all():
                return clean.cast(pl.Float64)

        # ISO-style dates only (YYYY-MM-DD) so day/month are never swapped
        for fmt in _DATE_FORMATS:
            parsed = clean.str.to_date(fmt, strict=False)
            if parsed.null_count() == clean.null_count():
                return parsed
        for fmt in _DATETIME_FORMATS:
            parsed = clean.str.to_datetime(fmt, strict=False)
            if parsed.null_count() == clean.null_count():
                return parsed
    except CATCH:
        pass
    return s


def smart_types(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([_convert_column(df[c]) for c in df.columns])


def peek_preview(f, sep: str, n_rows: int | None = None) -> pl.DataFrame:
    """Read just the first few rows of an uploaded CSV (fast, tiny memory)."""
    n_rows = n_rows or PREVIEW_ROWS
    limit = 5_000_000
    f.seek(0)
    chunk = f.read(limit)
    f.seek(0)
    if len(chunk) == limit:  # drop the possibly cut-off last line
        cut = chunk.rfind(b"\n")
        if cut > 0:
            chunk = chunk[:cut]
    return pl.read_csv(
        io.BytesIO(chunk),
        separator=sep,
        infer_schema_length=0,  # show everything as text
        encoding="utf8-lossy",
        truncate_ragged_lines=True,
        n_rows=n_rows,
    )


def read_csv_file(f, sep: str, infer_types: bool) -> pl.DataFrame:
    """Read a CSV with every column as text (never fails on mixed columns).

    If infer_types is True, columns that are safely numeric or ISO dates are then
    converted one by one; anything uncertain stays as text.
    """
    f.seek(0)
    df = pl.read_csv(
        f,
        separator=sep,
        infer_schema_length=0,  # all columns as text
        encoding="utf8-lossy",
        truncate_ragged_lines=True,
    )
    f.seek(0)
    if infer_types:
        try:
            df = smart_types(df)
        except CATCH:
            pass
    return df


def make_sheet_name(raw: str, used: set[str]) -> str:
    """Excel sheet names: max 31 chars, no []:*?/\\ and must be unique (case-insensitive)."""
    name = re.sub(r"[\[\]:*?/\\]+", "_", raw).strip().strip("'") or "Sheet"
    name = name[:31]
    candidate, i = name, 2
    while candidate.lower() in used:
        suffix = f"_{i}"
        candidate = name[: 31 - len(suffix)] + suffix
        i += 1
    used.add(candidate.lower())
    return candidate


MAX_XLSX_ROWS = 1_048_576  # Excel's hard limit per sheet (including the header row)
PROGRESS_EVERY = 20_000


def build_workbook_streaming(files, delim_label: str, infer_types: bool, on_progress):
    """Write CSV files into one workbook using xlsxwriter's constant-memory mode.

    Rows are streamed to disk instead of being held in memory, so large files
    (100 MB+) work. One CSV becomes one sheet; a CSV with more rows than Excel
    allows is split across several sheets automatically.
    """
    buf = io.BytesIO()
    used: set[str] = set()
    sheet_names: list[str] = []
    notes: list[str] = []
    total_rows = 0
    n_files = len(files)

    options = {
        "constant_memory": True,
        "strings_to_formulas": False,  # text starting with "=" stays text
        "strings_to_urls": False,
        "strings_to_numbers": False,
        "nan_inf_to_errors": True,
    }
    with Workbook(buf, options) as wb:
        header_fmt = wb.add_format({"bold": True, "bg_color": "#EDE9FE", "border": 1})
        date_fmt = wb.add_format({"num_format": "yyyy-mm-dd"})
        datetime_fmt = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})

        for fi, f in enumerate(files):
            f.seek(0)
            sample = f.read(8192)
            f.seek(0)
            sep = DELIMITERS[delim_label] or detect_delimiter(sample)

            on_progress(fi / n_files, f"Reading {f.name} ...")
            df = read_csv_file(f, sep, infer_types)
            n = df.height
            total_rows += n
            columns = df.columns

            # Column widths (from header + first rows) and date formats
            head = df.head(200)
            widths, col_fmts = [], []
            for c in columns:
                try:
                    longest = head[c].cast(pl.String).str.len_chars().max() or 0
                except CATCH:
                    longest = 10
                widths.append(min(max(len(str(c)), longest) + 2, 50))
                dtype = df.schema[c]
                if dtype == pl.Date:
                    col_fmts.append(date_fmt)
                elif dtype == pl.Datetime:
                    col_fmts.append(datetime_fmt)
                else:
                    col_fmts.append(None)

            base = Path(f.name).stem
            part = 0

            def new_sheet():
                nonlocal part
                part += 1
                raw = base if part == 1 else f"{base[:24]}_part{part}"
                name = make_sheet_name(raw, used)
                sheet_names.append(name)
                ws = wb.add_worksheet(name)
                ws.write_row(0, 0, [str(c) for c in columns], header_fmt)
                for j, (w, fm) in enumerate(zip(widths, col_fmts)):
                    ws.set_column(j, j, w, fm)
                ws.freeze_panes(1, 0)
                return ws

            ws = new_sheet()
            r = 1
            for i, row in enumerate(df.iter_rows()):
                if r >= MAX_XLSX_ROWS:
                    ws = new_sheet()
                    r = 1
                ws.write_row(r, 0, row)
                r += 1
                if i % PROGRESS_EVERY == 0:
                    on_progress((fi + i / max(n, 1)) / n_files, f"Writing {f.name}: {i:,} / {n:,} rows")

            if part > 1:
                notes.append(
                    f"{f.name} has more rows than one Excel sheet can hold "
                    f"({MAX_XLSX_ROWS:,}), so it was split across {part} sheets."
                )
            del df, head

    on_progress(1.0, "Finalising workbook ...")
    return buf.getvalue(), sheet_names, notes, total_rows


# ----------------------------------------------------------------------------
# Header + sidebar
# ----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <h1>📊 Excel ⇄ CSV Converter</h1>
        <p>Convert Excel sheets to CSV, or combine CSV files into one Excel workbook.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

def steps_html(steps: list[str]) -> str:
    return "".join(
        f'<div class="sb-step"><div class="sb-num">{i}</div><div class="sb-txt">{t}</div></div>'
        for i, t in enumerate(steps, 1)
    )


with st.sidebar:
    st.markdown(
        '<div class="sb-brand">📊 Converter Toolkit</div>'
        '<div class="sb-sub">Excel ⇄ CSV, fast and private-friendly.</div>',
        unsafe_allow_html=True,
    )

    # ---- How it works ----
    st.markdown('<div class="sb-heading">📖 How it works</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sb-group">📊 Excel → CSV</div>'
        + steps_html(
            [
                "Upload an <b>.xlsx / .xlsm / .xls</b> file.",
                "Pick the <b>sheet</b> you want from the chips.",
                "Check the <b>preview</b> (all rows), columns and stats.",
                "In the <b>Export</b> tab, set the delimiter and header, then download <b>filename_sheetname.csv</b> or every sheet as a ZIP.",
            ]
        )
        + '<div class="sb-group">🔄 CSV → Excel</div>'
        + steps_html(
            [
                "Upload <b>one or more</b> CSV files.",
                "Choose the <b>delimiter</b> or leave it on auto-detect.",
                "Name the workbook and click <b>Download Excel</b> (one sheet per CSV).",
                "Scroll down to preview the <b>first 10 rows</b> of each file.",
            ]
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    # ---- Tips ----
    st.markdown('<div class="sb-heading">💡 Good to know</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sb-tip">🔢 CSV → Excel keeps every column as <b>text</b> by default, '
        "so IDs and long numbers are never altered. Tick <i>Detect numbers &amp; dates</i> "
        "if you need real numbers.</div>"
        '<div class="sb-tip">📑 Excel sheet names are limited to <b>31 characters</b>; '
        "longer CSV names are shortened automatically.</div>"
        '<div class="sb-tip">👀 Excel → CSV previews show <b>every row</b>; CSV → Excel previews show the first <b>10 rows</b>. '
        "Downloads always contain <b>all rows</b>.</div>"
        '<div class="sb-tip">📦 Big CSVs (10 MB+) start converting when you click '
        "<b>Build Excel file</b>. A 100 MB file can take a minute or two, and files over "
        "1,048,576 rows are split across several sheets because of Excel's limit.</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="sb-foot">Built with Streamlit &amp; Polars</div>',
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Page 1: Excel -> CSV
# ----------------------------------------------------------------------------
def excel_to_csv_page():
    uploaded = st.file_uploader(
        "Drop your Excel file here",
        type=["xlsx", "xlsm", "xls"],
        label_visibility="collapsed",
        key="excel_uploader",
    )

    if uploaded is None:
        empty_state(
            [
                ("📂", "Load every sheet", "All sheets in the workbook are read automatically."),
                ("👀", "Preview instantly", "Check rows, column types and statistics before exporting."),
                ("💾", "Export your way", "Named as filename_sheetname.csv, with your delimiter."),
            ]
        )
        return

    try:
        sheets = load_all_sheets(uploaded.getvalue())
    except Exception as e:
        st.error(f"Could not read the file: {e}")
        return

    if not sheets:
        st.warning("No sheets found in this workbook.")
        return

    sheet_names = list(sheets.keys())
    base = safe_name(Path(uploaded.name).stem)

    m1, m2, m3 = st.columns(3)
    m1.metric("📁 File", uploaded.name if len(uploaded.name) < 24 else uploaded.name[:21] + "...")
    m2.metric("🗂️ Sheets", len(sheet_names))
    m3.metric("📦 Size", human_size(uploaded.size))

    st.markdown("### 🗂️ Choose a sheet")

    def sheet_label(s: str) -> str:
        return f"{s}  ({sheets[s].height:,} rows × {sheets[s].width} cols)"

    widget_key = f"sheet_choice_{uploaded.name}_{uploaded.size}"
    if len(sheet_names) <= 8:
        selected = st.radio(
            "Select the sheet to preview and export",
            sheet_names,
            format_func=sheet_label,
            horizontal=True,
            key=widget_key,
        )
    else:
        selected = st.selectbox(
            "Select the sheet to preview and export",
            sheet_names,
            format_func=sheet_label,
            key=widget_key,
        )

    df = sheets[selected]

    tab_preview, tab_cols, tab_stats, tab_export = st.tabs(
        ["👀 Preview", "🧬 Columns", "📈 Statistics", "💾 Export"]
    )

    with tab_preview:
        k1, k2, k3 = st.columns(3)
        k1.metric("Rows", f"{df.height:,}")
        k2.metric("Columns", f"{df.width:,}")
        k3.metric("Null cells", f"{sum(df.null_count().row(0)):,}")

        if df.height == 0:
            st.info("This sheet is empty.")
        else:
            shown = df.head(EXCEL_PREVIEW_MAX)
            show_df(shown)
            if df.height > EXCEL_PREVIEW_MAX:
                st.caption(
                    f"Showing the first {EXCEL_PREVIEW_MAX:,} of {df.height:,} rows "
                    "(capped so the browser stays responsive). The export contains every row."
                )
            else:
                st.caption(f"Showing all {df.height:,} rows.")

    with tab_cols:
        nulls = df.null_count().row(0)
        show_df(
            pl.DataFrame(
                {
                    "Column": df.columns,
                    "Type": [str(t) for t in df.dtypes],
                    "Nulls": list(nulls),
                    "Unique": [df[c].n_unique() for c in df.columns],
                }
            ),
            hide_index=True,
        )

    with tab_stats:
        if df.height == 0:
            st.info("This sheet is empty.")
        else:
            try:
                show_df(df.describe())
            except Exception as e:
                st.warning(f"Could not compute statistics for this sheet: {e}")

    with tab_export:
        st.markdown("#### ⚙️ CSV options")
        oc1, oc2 = st.columns(2)
        with oc1:
            delimiter_label = st.selectbox(
                "CSV delimiter",
                ["Comma ( , )", "Semicolon ( ; )", "Tab", "Pipe ( | )"],
                key="csv_out_delimiter",
            )
        with oc2:
            st.write("")  # vertical alignment
            include_header = st.toggle("Include header row", value=True, key="csv_out_header")
        out_delimiter = {
            "Comma ( , )": ",",
            "Semicolon ( ; )": ";",
            "Tab": "\t",
            "Pipe ( | )": "|",
        }[delimiter_label]

        st.divider()

        csv_name = f"{base}_{safe_name(selected)}.csv"
        csv_bytes = to_csv_bytes(df, out_delimiter, include_header)

        st.markdown("#### Selected sheet")
        st.markdown(f'<span class="file-pill">{html.escape(csv_name)}</span>', unsafe_allow_html=True)
        st.caption(f"{df.height:,} rows · {df.width} columns · about {human_size(len(csv_bytes))}")
        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
            type="primary",
        )

        if len(sheet_names) > 1:
            st.divider()
            st.markdown("#### Every sheet at once")
            st.caption("All sheets as separate CSV files in one ZIP, each named filename_sheetname.csv.")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for s in sheet_names:
                    zf.writestr(
                        f"{base}_{safe_name(s)}.csv",
                        to_csv_bytes(sheets[s], out_delimiter, include_header),
                    )
            st.download_button(
                "📦 Download all sheets (ZIP)",
                data=buf.getvalue(),
                file_name=f"{base}_all_sheets.zip",
                mime="application/zip",
            )


# ----------------------------------------------------------------------------
# Page 2: CSV -> Excel
# ----------------------------------------------------------------------------
AUTO_BUILD_BYTES = 10 * 1024 * 1024  # build automatically below this total upload size


def csv_to_excel_page():
    files = st.file_uploader(
        "Drop one or more CSV files here",
        type=["csv", "tsv", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="csv_uploader",
    )

    if not files:
        empty_state(
            [
                ("📄", "One or many CSVs", "Upload several files and each becomes its own sheet."),
                ("🔍", "Smart delimiter", "Comma, semicolon, tab or pipe is detected automatically."),
                ("📗", "Built for big files", "Large CSVs are streamed, and split if they exceed Excel's row limit."),
            ]
        )
        return

    o1, o2 = st.columns(2)
    with o1:
        delim_label = st.selectbox(
            "Delimiter used in your CSV file(s)",
            list(DELIMITERS.keys()),
            key="csv_in_delimiter",
        )
    with o2:
        st.write("")  # vertical alignment
        infer_types = st.checkbox(
            "Detect numbers & dates",
            value=False,
            help="Off (recommended): all columns stay as text, so IDs and long numbers are kept exactly. "
            "On: columns that are clearly numeric or ISO dates (YYYY-MM-DD) are converted. "
            "Columns with leading zeros, 16+ digits or mixed content stay as text.",
            key="csv_infer_types",
        )

    # Read only the header line of each file (fast, no big memory use)
    infos = []
    for f in files:
        f.seek(0)
        sample = f.read(8192)
        f.seek(0)
        sep = DELIMITERS[delim_label] or detect_delimiter(sample)
        try:
            infos.append((f, peek_preview(f, sep)))
        except CATCH as e:
            st.error(f"Could not read **{f.name}**: {e}")

    if not infos:
        return

    good_files = [f for f, _ in infos]
    total_size = sum(f.size for f in good_files)

    m1, m2, m3 = st.columns(3)
    m1.metric("📄 CSV files", len(good_files))
    m2.metric("🧬 Columns", sum(p.width for _, p in infos))
    m3.metric("📦 Uploaded", human_size(total_size))

    # ---- Export ----
    st.markdown("### 💾 Export to Excel")
    default_name = Path(good_files[0].name).stem if len(good_files) == 1 else "combined"
    wb_name = st.text_input("Workbook name (without .xlsx)", value=default_name, key="wb_name")
    wb_name = safe_name(wb_name) or "converted"
    xlsx_name = f"{wb_name}.xlsx"

    sig = (tuple((f.name, f.size) for f in good_files), delim_label, infer_types)
    state = st.session_state.get("xlsx_result")
    if state is not None and state["sig"] != sig:
        state = None

    clicked = False
    if state is None and total_size > AUTO_BUILD_BYTES:
        st.info(
            f"Large upload ({human_size(total_size)}). Building the workbook can take a minute or two, "
            "so it starts when you click the button."
        )
        clicked = st.button("⚙️ Build Excel file", key="build_excel_btn")

    if state is None and (total_size <= AUTO_BUILD_BYTES or clicked):
        bar = st.progress(0.0, text="Starting ...")

        def on_progress(frac: float, text: str):
            bar.progress(min(max(frac, 0.0), 1.0), text=text)

        try:
            data, sheet_names, notes, total_rows = build_workbook_streaming(
                good_files, delim_label, infer_types, on_progress
            )
            state = {
                "sig": sig,
                "data": data,
                "sheets": sheet_names,
                "notes": notes,
                "rows": total_rows,
            }
            st.session_state["xlsx_result"] = state
        except CATCH as e:
            st.session_state.pop("xlsx_result", None)
            st.error(f"Could not build the Excel file: {e}")
        finally:
            bar.empty()

    if state is not None:
        for note in state["notes"]:
            st.warning(note)
        st.markdown(f'<span class="file-pill">{html.escape(xlsx_name)}</span>', unsafe_allow_html=True)
        sheet_list = ", ".join(state["sheets"])
        st.caption(
            f"{state['rows']:,} rows · {len(state['sheets'])} sheet(s): {sheet_list} · "
            f"about {human_size(len(state['data']))}"
        )
        st.download_button(
            "⬇️ Download Excel",
            data=state["data"],
            file_name=xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="download_excel_btn",
        )

    # ---- Preview: first rows of each file ----
    st.markdown("### 👀 Preview")
    for f, prev in infos:
        with st.expander(
            f"{f.name}  ({prev.width} columns · {human_size(f.size)})",
            expanded=len(infos) == 1,
        ):
            if prev.width == 0:
                st.info("No columns found in this file.")
            elif prev.height == 0:
                st.info("This file has a header row but no data rows.")
            else:
                show_df(prev)
                if prev.height < PREVIEW_ROWS:
                    st.caption(f"Showing all {prev.height} row(s) of this file.")
                else:
                    st.caption(f"Showing the first {PREVIEW_ROWS} rows. The Excel file will contain every row.")


# ----------------------------------------------------------------------------
# Main layout
# ----------------------------------------------------------------------------
tab_x2c, tab_c2x = st.tabs(["📊 Excel → CSV", "🔄 CSV → Excel"])
with tab_x2c:
    excel_to_csv_page()
with tab_c2x:
    csv_to_excel_page()
