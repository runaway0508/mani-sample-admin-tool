"""Small inventory admin tool: login, search, add/edit/delete items, low-stock filter, CSV export.

Run: ADMIN_PASSWORD=change-me uvicorn app:app --reload   then open http://127.0.0.1:8000
"""
import csv
import hmac
import io
import os
import secrets
import sqlite3

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

DB = os.getenv("APP_DB", "inventory.db")
PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
SESSIONS: set[str] = set()

app = FastAPI(title="Inventory admin")
tpl = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0, reorder_at INTEGER NOT NULL DEFAULT 0,
        updated TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


def authed(req: Request) -> bool:
    return req.cookies.get("sid") in SESSIONS


def back(path="/"):
    return RedirectResponse(path, status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(req: Request, error: str = ""):
    return tpl.TemplateResponse(req, "login.html", {"error": error})


@app.post("/login")
def login(password: str = Form(...)):
    if not hmac.compare_digest(password, PASSWORD):
        return back("/login?error=1")
    sid = secrets.token_urlsafe(24)
    SESSIONS.add(sid)
    r = back()
    r.set_cookie("sid", sid, httponly=True, samesite="lax")
    return r


@app.get("/logout")
def logout(req: Request):
    SESSIONS.discard(req.cookies.get("sid"))
    return back("/login")


@app.get("/", response_class=HTMLResponse)
def index(req: Request, q: str = "", low: int = 0, msg: str = ""):
    if not authed(req):
        return back("/login")
    sql, args = "SELECT * FROM items WHERE (sku LIKE ? OR name LIKE ?)", [f"%{q}%", f"%{q}%"]
    if low:
        sql += " AND qty <= reorder_at"
    with db() as con:
        items = con.execute(sql + " ORDER BY name", args).fetchall()
        n_low = con.execute("SELECT COUNT(*) FROM items WHERE qty <= reorder_at").fetchone()[0]
    return tpl.TemplateResponse(req, "index.html", {"items": items, "q": q, "low": low, "n_low": n_low, "msg": msg})


@app.post("/items")
def save(req: Request, sku: str = Form(...), name: str = Form(...), qty: int = Form(...),
         reorder_at: int = Form(0), item_id: int = Form(0)):
    if not authed(req):
        return back("/login")
    if qty < 0 or reorder_at < 0 or not sku.strip() or not name.strip():
        return back("/?msg=Invalid+values")
    with db() as con:
        try:
            if item_id:
                con.execute("UPDATE items SET sku=?,name=?,qty=?,reorder_at=?,updated=CURRENT_TIMESTAMP WHERE id=?",
                            (sku.strip(), name.strip(), qty, reorder_at, item_id))
            else:
                con.execute("INSERT INTO items(sku,name,qty,reorder_at) VALUES(?,?,?,?)",
                            (sku.strip(), name.strip(), qty, reorder_at))
        except sqlite3.IntegrityError:
            return back("/?msg=SKU+already+exists")
    return back("/?msg=Saved")


@app.post("/items/{item_id}/delete")
def delete(req: Request, item_id: int):
    if not authed(req):
        return back("/login")
    with db() as con:
        con.execute("DELETE FROM items WHERE id=?", (item_id,))
    return back("/?msg=Deleted")


@app.get("/export.csv")
def export(req: Request):
    if not authed(req):
        return back("/login")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sku", "name", "qty", "reorder_at", "updated"])
    with db() as con:
        for r in con.execute("SELECT sku,name,qty,reorder_at,updated FROM items ORDER BY name"):
            w.writerow(list(r))
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=inventory.csv"})
