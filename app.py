"""
夏日出逃计划2 — Flask 后端
支持 SQLite (本地开发) 和 PostgreSQL (Render 等云平台)
"""

import json
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g

app = Flask(__name__)

# ── 数据库选择 ─────────────────────────────────────────────
DB_TYPE = os.environ.get("DB_TYPE", "sqlite")

if DB_TYPE == "postgres":
    import pg8000.native
    import urllib.parse
    USE_POSTGRES = True
else:
    import sqlite3
    USE_POSTGRES = False
    DATABASE = os.path.join(os.path.dirname(__file__), "data.db")

# ── 数据模型 ─────────────────────────────────────────────

def default_plan():
    return {
        "free_dates_sol": [],
        "free_dates_shu": [],
        "destinations": [
            {"name": "江浙沪", "description": "小预算 💰", "votes_sol": 0, "votes_shu": 0},
            {"name": "广西/云南", "description": "穷游富游终不似少年游", "votes_sol": 0, "votes_shu": 0}
        ],
        "custom_destinations": [],
        "itinerary": [],
        "checklist": [
            {"id": 1, "category": "🧳 行李", "content": "换洗衣物", "checked_sol": False, "checked_shu": False},
            {"id": 2, "category": "🧳 行李", "content": "泳衣", "checked_sol": False, "checked_shu": False},
            {"id": 3, "category": "🧳 行李", "content": "防晒霜", "checked_sol": False, "checked_shu": False},
            {"id": 4, "category": "🧳 行李", "content": "墨镜", "checked_sol": False, "checked_shu": False},
            {"id": 5, "category": "🧳 行李", "content": "充电器/充电宝", "checked_sol": False, "checked_shu": False},
            {"id": 6, "category": "📄 证件", "content": "身份证", "checked_sol": False, "checked_shu": False},
            {"id": 7, "category": "📄 证件", "content": "学生证", "checked_sol": False, "checked_shu": False},
            {"id": 8, "category": "📄 证件", "content": "车票/机票", "checked_sol": False, "checked_shu": False},
            {"id": 9, "category": "💊 药品", "content": "晕车药", "checked_sol": False, "checked_shu": False},
            {"id": 10, "category": "💊 药品", "content": "创可贴", "checked_sol": False, "checked_shu": False},
            {"id": 11, "category": "💊 药品", "content": "防蚊液", "checked_sol": False, "checked_shu": False},
            {"id": 12, "category": "🎒 其他", "content": "相机", "checked_sol": False, "checked_shu": False},
            {"id": 13, "category": "🎒 其他", "content": "零食", "checked_sol": False, "checked_shu": False},
            {"id": 14, "category": "🎒 其他", "content": "雨伞", "checked_sol": False, "checked_shu": False},
        ],
        "messages": [],
    }

# ── 数据库连接 ─────────────────────────────────────────────

def get_conn():
    if USE_POSTGRES:
        db_url = os.environ["DATABASE_URL"]
        parsed = urllib.parse.urlparse(db_url)
        conn = pg8000.native.Connection(
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:] if parsed.path else None
        )
        conn.autocommit = True
        return conn
    else:
        conn = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_conn()
    if USE_POSTGRES:
        conn.run("""
            CREATE TABLE IF NOT EXISTS invitation (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.run("""
            CREATE TABLE IF NOT EXISTS plan (
                id SERIAL PRIMARY KEY,
                invitation_id TEXT UNIQUE REFERENCES invitation(id),
                data TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    else:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS invitation (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                accepted_at TEXT,
                status      TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS plan (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                invitation_id  TEXT UNIQUE,
                data           TEXT NOT NULL DEFAULT '{}',
                updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (invitation_id) REFERENCES invitation(id)
            );
        """)
        conn.commit()
        conn.close()

# ── 请求级数据库连接 ───────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = get_conn()
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        if USE_POSTGRES:
            db.close()
        else:
            db.commit()
            db.close()

# ── API ───────────────────────────────────────────────────

@app.route("/api/invitation/create", methods=["POST"])
def create_invitation():
    inv_id = uuid.uuid4().hex[:8]
    db = get_db()
    if USE_POSTGRES:
        db.run("INSERT INTO invitation (id) VALUES ($1)", (inv_id,))
        db.run("INSERT INTO plan (invitation_id, data) VALUES ($1, $2)",
               (inv_id, json.dumps(default_plan(), ensure_ascii=False)))
    else:
        db.execute("INSERT INTO invitation (id) VALUES (?)", (inv_id,))
        db.execute("INSERT INTO plan (invitation_id, data) VALUES (?, ?)",
                   (inv_id, json.dumps(default_plan(), ensure_ascii=False)))
        db.commit()
    return jsonify({"id": inv_id, "url": f"/plan/{inv_id}"})


@app.route("/api/invitation/<inv_id>/accept", methods=["POST"])
def accept_invitation(inv_id):
    db = get_db()
    if USE_POSTGRES:
        rows = db.run("SELECT id FROM invitation WHERE id = $1", (inv_id,))
        if not rows:
            return jsonify({"error": "not found"}), 404
        db.run("UPDATE invitation SET status = 'accepted', accepted_at = NOW() WHERE id = $1", (inv_id,))
    else:
        cur = db.execute("SELECT id FROM invitation WHERE id = ?", (inv_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        db.execute("UPDATE invitation SET status = 'accepted', accepted_at = datetime('now','localtime') WHERE id = ?",
                   (inv_id,))
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/plan/<inv_id>", methods=["GET"])
def get_plan(inv_id):
    db = get_db()
    if USE_POSTGRES:
        rows = db.run("SELECT data, updated_at FROM plan WHERE invitation_id = $1", (inv_id,))
        if not rows:
            return jsonify({"error": "not found"}), 404
        cols = [c["name"] for c in db.columns]
        row = dict(zip(cols, rows[0]))
    else:
        row = db.execute("SELECT data, updated_at FROM plan WHERE invitation_id = ?", (inv_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
    return jsonify({"data": json.loads(row["data"]), "updated_at": str(row["updated_at"])})


@app.route("/api/plan/<inv_id>", methods=["POST"])
def update_plan(inv_id):
    db = get_db()
    new_data = request.get_json(force=True)
    if USE_POSTGRES:
        rows = db.run("SELECT id FROM plan WHERE invitation_id = $1", (inv_id,))
        if not rows:
            return jsonify({"error": "not found"}), 404
        db.run("UPDATE plan SET data = $1, updated_at = NOW() WHERE invitation_id = $2",
               (json.dumps(new_data, ensure_ascii=False), inv_id))
    else:
        cur = db.execute("SELECT id FROM plan WHERE invitation_id = ?", (inv_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        db.execute("UPDATE plan SET data = ?, updated_at = datetime('now','localtime') WHERE invitation_id = ?",
                   (json.dumps(new_data, ensure_ascii=False), inv_id))
        db.commit()
    return jsonify({"ok": True})


# ── 页面路由 ───────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html", role="sol", inv_id=None)

@app.route("/plan/<inv_id>")
def plan_view(inv_id):
    role = "shu"
    return render_template("index.html", role=role, inv_id=inv_id)

@app.route("/setup/<inv_id>")
def setup_view(inv_id):
    role = "sol"
    return render_template("index.html", role=role, inv_id=inv_id)


# ── 启动 ───────────────────────────────────────────────────

# Gunicorn 启动时也会执行这里，确保数据库表已创建
try:
    init_db()
except Exception:
    pass  # 环境变量未就绪时跳过，由 __main__ 再试

if __name__ == "__main__":
    init_db()
    print("Summer Escape Plan 2 - Backend started")
    print("   Open http://localhost:5000 to create a new invitation")
    app.run(debug=True, host="0.0.0.0", port=5000)
