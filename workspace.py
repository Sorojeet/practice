"""Workspace: the files a visitor uploads, read once into one DuckDB database and shared by the viewer and every tool."""
import functools, os, tempfile, time, uuid

import duckdb
import polars as pl
from flask import Blueprint, current_app, jsonify, request

from engine import file_kind, kind_of, q, read_frames, read_one, rm, to_duckdb

WSS, TTL, MAX_FILES = {}, 7200, 5
MAX_ROWS = int(os.environ.get("TOOL_MAX_ROWS", 1_000_000))
ALLOWED = (".xlsx", ".xlsm", ".xls", ".xlsb", ".ods", ".csv", ".tsv", ".txt")
bp = Blueprint("ws", __name__, url_prefix="/api/ws")


class UserError(ValueError):
    """A problem the visitor can fix; the message is shown to them."""


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
            current_app.logger.exception("request failed")
            return jsonify(error="Something went wrong while processing the file. Please try again."), 500
    return wrapper


def body():
    return request.get_json(silent=True) or {}


# ---------- store ----------
def _close(token):
    ws = WSS.pop(token, None)
    if not ws:
        return
    for f in ws["files"].values():
        if f["path"]:
            rm(f["path"])
    for con in (ws.get("compare", {}).get("con"), ws["con"]):
        try:
            if con:
                con.close()
        except Exception:
            pass


def create():
    now = time.time()
    for k in [k for k, v in WSS.items() if now - v["t"] > TTL]:
        _close(k)
    token = uuid.uuid4().hex
    WSS[token] = {"t": now, "con": duckdb.connect(), "files": {}, "next": 1}
    return token


def get(token):
    ws = WSS.get(token)
    if not ws:
        raise UserError("Your files have expired. Upload the file again.")
    ws["t"] = time.time()
    return ws


def find(ws, fid, sid):
    f = ws["files"].get(fid)
    if not f:
        raise UserError("That file is no longer open. Pick another file or upload it again.")
    s = next((x for x in f["sheets"] if x["id"] == sid), None)
    if not s:
        raise UserError("Sheet not found.")
    return f, s


def sheet_df(ws, fid, sid):
    """A sheet as a Polars DataFrame (the data itself lives in DuckDB)."""
    _, s = find(ws, fid, sid)
    return ws["con"].cursor().execute(f"SELECT * FROM {q(s['table'])}").pl()


def _register(ws, fid, sid, name, df, hdr):
    table = f"t{fid}_{sid}"
    to_duckdb(ws["con"].cursor(), table, df)
    return {"id": sid, "name": name, "rows": df.height, "hdr": hdr, "table": table,
            "cols": [{"name": n, "numeric": df[n].dtype.is_numeric(), "type": kind_of(df[n].dtype)} for n in df.columns]}


def add_file(ws, name, frames, path=None, kind="derived"):
    if len(ws["files"]) >= MAX_FILES:
        raise UserError(f"You can keep {MAX_FILES} files open at once. Remove one first.")
    for n, d in frames:
        if d.height > MAX_ROWS:
            raise UserError(f"Sheet '{n}' has {d.height:,} rows. The limit is {MAX_ROWS:,} rows per sheet.")
    fid = ws["next"]
    ws["next"] += 1
    f = {"id": fid, "name": name, "path": path, "kind": kind, "sheets": []}
    ws["files"][fid] = f
    try:
        f["sheets"] = [_register(ws, fid, i, n, d, 1) for i, (n, d) in enumerate(frames)]
    except Exception:
        ws["files"].pop(fid, None)
        raise
    return f


def state(ws, token, **extra):
    files = [{"id": f["id"], "name": f["name"], "derived": f["path"] is None,
              "sheets": [{k: s[k] for k in ("id", "name", "rows", "hdr", "cols")} for s in f["sheets"]]} for f in ws["files"].values()]
    return {"ws": token, "files": files, **extra}


# ---------- endpoints ----------
@bp.post("/upload")
@api
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        raise UserError("Choose a file first.")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        raise UserError("Unsupported file type. Use xlsx, xls, xlsb, ods, csv, tsv or txt.")
    token = request.form.get("ws")
    ws = WSS.get(token) if token else None
    if ws:
        ws["t"] = time.time()
    else:
        token = create()
        ws = WSS[token]
    fd, path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        f.save(path)
        frames = read_frames(path, f.filename)
        if not frames:
            raise UserError("This file has no data.")
        file = add_file(ws, f.filename, frames, path, file_kind(f.filename))
    except UserError:
        rm(path)
        raise
    except Exception as e:
        rm(path)
        raise UserError(f"Could not read this file: {e}")
    return jsonify(state(ws, token, file=file["id"]))


@bp.post("/state")
@api
def get_state():
    j = body()
    return jsonify(state(get(j.get("ws")), j.get("ws")))


@bp.post("/header")
@api
def header():
    """Use another row as the header. The sheet is read again and its column types are detected again."""
    j = body()
    ws = get(j.get("ws"))
    f, s = find(ws, j.get("file"), j.get("sheet"))
    if f["path"] is None:
        raise UserError("This file was made from cleaned data and already has its own header row.")
    try:
        row = int(j.get("row", 1))
        if row < 1:
            raise ValueError("The header row must be 1 or higher.")
        d = read_one(f["path"], f["kind"], s["name"], row)
        if not d.width:
            raise ValueError("No columns were found at that row.")
    except Exception as e:
        raise UserError(f"Could not use row {j.get('row')} as the header: {e}")
    s.update(_register(ws, f["id"], s["id"], s["name"], d, row))
    return jsonify(state(ws, j.get("ws")))


@bp.post("/remove")
@api
def remove():
    j = body()
    ws = get(j.get("ws"))
    f = ws["files"].pop(j.get("file"), None)
    if f:
        for s in f["sheets"]:
            ws["con"].cursor().execute(f"DROP TABLE IF EXISTS {q(s['table'])}")
        if f["path"]:
            rm(f["path"])
    return jsonify(state(ws, j.get("ws")))


@bp.post("/clear")
@api
def clear():
    _close(body().get("ws"))
    return jsonify(ok=True)
