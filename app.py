"""
夏日出逃计划2 — Flask 后端
支持 Vercel KV (Redis) 或 SQLite (本地开发)
"""

import json
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g

app = Flask(__name__)

# ── 数据库选择 ─────────────────────────────────────────────
redis_url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
redis_token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")

if redis_url and redis_token:
    from upstash_redis import Redis
    redis = Redis(url=redis_url, token=redis_token)
    USE_REDIS = True
else:
    import sqlite3
    USE_REDIS = False
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

# ── SQLite helpers (local dev) ────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    if not USE_REDIS:
        db = g.pop("db", None)
        if db:
            db.close()

def init_db_sqlite():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
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
    db.commit()
    db.close()

# ── API ───────────────────────────────────────────────────

@app.route("/api/invitation/create", methods=["POST"])
def create_invitation():
    inv_id = uuid.uuid4().hex[:8]
    if USE_REDIS:
        invitation = {
            "id": inv_id,
            "created_at": datetime.now().isoformat(),
            "accepted_at": None,
            "status": "pending"
        }
        redis.set(f"invitation:{inv_id}", json.dumps(invitation, ensure_ascii=False))
        redis.set(f"plan:{inv_id}", json.dumps(default_plan(), ensure_ascii=False))
    else:
        db = get_db()
        db.execute("INSERT INTO invitation (id) VALUES (?)", (inv_id,))
        db.execute("INSERT INTO plan (invitation_id, data) VALUES (?, ?)",
                   (inv_id, json.dumps(default_plan(), ensure_ascii=False)))
        db.commit()
    return jsonify({"id": inv_id, "url": f"/plan/{inv_id}"})


@app.route("/api/invitation/<inv_id>/accept", methods=["POST"])
def accept_invitation(inv_id):
    if USE_REDIS:
        raw = redis.get(f"invitation:{inv_id}")
        if not raw:
            return jsonify({"error": "not found"}), 404
        inv = json.loads(raw)
        inv["status"] = "accepted"
        inv["accepted_at"] = datetime.now().isoformat()
        redis.set(f"invitation:{inv_id}", json.dumps(inv, ensure_ascii=False))
    else:
        db = get_db()
        cur = db.execute("SELECT id FROM invitation WHERE id=?", (inv_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        db.execute("UPDATE invitation SET status='accepted', accepted_at=datetime('now','localtime') WHERE id=?",
                   (inv_id,))
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/plan/<inv_id>", methods=["GET"])
def get_plan(inv_id):
    if USE_REDIS:
        data = redis.get(f"plan:{inv_id}")
        if not data:
            return jsonify({"error": "not found"}), 404
        return jsonify({"data": json.loads(data), "updated_at": datetime.now().isoformat()})
    else:
        db = get_db()
        row = db.execute("SELECT data, updated_at FROM plan WHERE invitation_id=?", (inv_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify({"data": json.loads(row["data"]), "updated_at": row["updated_at"]})


@app.route("/api/plan/<inv_id>", methods=["POST"])
def update_plan(inv_id):
    if USE_REDIS:
        if not redis.exists(f"plan:{inv_id}"):
            return jsonify({"error": "not found"}), 404
        new_data = request.get_json(force=True)
        redis.set(f"plan:{inv_id}", json.dumps(new_data, ensure_ascii=False))
    else:
        db = get_db()
        cur = db.execute("SELECT id FROM plan WHERE invitation_id=?", (inv_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        new_data = request.get_json(force=True)
        db.execute("UPDATE plan SET data=?, updated_at=datetime('now','localtime') WHERE invitation_id=?",
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

if __name__ == "__main__":
    if not USE_REDIS:
        init_db_sqlite()
    print("Summer Escape Plan 2 - Backend started")
    print("   Open http://localhost:5000 to create a new invitation")
    app.run(debug=True, host="0.0.0.0", port=5000)
