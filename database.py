"""
追星助手 · 数据库底座
SQLite 数据库，包含 idols / posts / tmis / schedules 四张表 + 全文搜索
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "star_tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS idols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    group_name TEXT,
    weibo_uid TEXT UNIQUE,
    birthday TEXT,
    avatar_url TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    mid TEXT,
    idol_id INTEGER REFERENCES idols(id),
    text TEXT,
    is_retweet INTEGER DEFAULT 0,
    original_text TEXT,
    reposts_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    pics_count INTEGER DEFAULT 0,
    url TEXT,
    created_at TEXT,
    scraped_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tmis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idol_id INTEGER REFERENCES idols(id),
    content TEXT NOT NULL,
    category TEXT,
    confidence TEXT CHECK(confidence IN ('high', 'medium', 'low')),
    quote TEXT,
    post_id INTEGER REFERENCES posts(id),
    post_url TEXT,
    post_date TEXT,
    post_likes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idol_id INTEGER REFERENCES idols(id),
    title TEXT NOT NULL,
    event_type TEXT,
    start_date TEXT,
    end_date TEXT,
    location TEXT,
    description TEXT,
    source_post_id INTEGER REFERENCES posts(id),
    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_tmis_idol ON tmis(idol_id);
CREATE INDEX IF NOT EXISTS idx_tmis_category ON tmis(category);
CREATE INDEX IF NOT EXISTS idx_posts_idol ON posts(idol_id);

CREATE TABLE IF NOT EXISTS counselings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idol_id INTEGER REFERENCES idols(id),
    content TEXT NOT NULL,
    quote TEXT DEFAULT '',
    post_id INTEGER REFERENCES posts(id),
    post_url TEXT DEFAULT '',
    post_date TEXT DEFAULT '',
    post_likes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_counselings_idol ON counselings(idol_id);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"数据库已初始化：{DB_PATH}")


def ensure_idol(conn: sqlite3.Connection, name: str, weibo_uid: str,
                group_name: str = None, **kwargs) -> int:
    """插入或获取 idol，返回 id"""
    cur = conn.execute("SELECT id FROM idols WHERE weibo_uid = ?", (weibo_uid,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(
        "INSERT INTO idols (name, group_name, weibo_uid, birthday, notes) VALUES (?,?,?,?,?)",
        (name, group_name, weibo_uid, kwargs.get("birthday"), kwargs.get("notes"))
    )
    return cur.lastrowid


def insert_posts(conn: sqlite3.Connection, posts: list[dict], idol_id: int):
    cur = conn.executemany("""
        INSERT OR IGNORE INTO posts (id, mid, idol_id, text, is_retweet, original_text,
            reposts_count, comments_count, likes_count, pics_count, url, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        (
            p["id"], p.get("mid"), idol_id, p["text"],
            1 if p.get("is_retweet") else 0, p.get("original_text", ""),
            p.get("reposts", 0), p.get("comments", 0), p.get("likes", 0),
            p.get("pics", 0), p.get("url", ""), p.get("created_at", "")
        )
        for p in posts
    ])
    return cur.rowcount


def insert_tmis(conn: sqlite3.Connection, tmis: list[dict], idol_id: int):
    cur = conn.executemany("""
        INSERT INTO tmis (idol_id, content, category, confidence, quote, post_id, post_url, post_date, post_likes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, [
        (
            idol_id, t["content"], t["category"], t.get("confidence", "low"),
            t.get("quote", ""), t.get("post_id"), t.get("post_url", ""),
            t.get("post_date", ""), t.get("post_likes", 0)
        )
        for t in tmis
    ])
    return cur.rowcount


def search_tmi(keyword: str, category: str = None, idol_id: int = None,
               limit: int = 20) -> list[dict]:
    """搜索 TMI（LIKE 匹配 content + quote，支持中文）"""
    conn = get_connection()
    pattern = f"%{keyword}%"
    conditions = ["(t.content LIKE ? OR t.quote LIKE ?)"]
    params = [pattern, pattern]

    if category:
        conditions.append("t.category = ?")
        params.append(category)
    if idol_id:
        conditions.append("t.idol_id = ?")
        params.append(idol_id)

    sql = f"""
        SELECT t.*, i.name as idol_name FROM tmis t
        JOIN idols i ON t.idol_id = i.id
        WHERE {' AND '.join(conditions)}
        ORDER BY t.post_date DESC LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_idol_tmis(idol_id: int, category: str = None, confidence: str = None) -> list[dict]:
    """获取指定 idol 的 TMI 列表，可按分类/可信度筛选"""
    conn = get_connection()
    conditions = ["idol_id = ?"]
    params = [idol_id]
    if category:
        conditions.append("category = ?")
        params.append(category)
    if confidence:
        conditions.append("confidence = ?")
        params.append(confidence)
    sql = f"SELECT * FROM tmis WHERE {' AND '.join(conditions)} ORDER BY post_date DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tmi_categories(idol_id: int) -> list[dict]:
    """统计某 idol 的 TMI 分类分布"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM tmis WHERE idol_id = ? GROUP BY category ORDER BY cnt DESC",
        (idol_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    conn = get_connection()
    return {
        "idols": conn.execute("SELECT COUNT(*) as n FROM idols").fetchone()["n"],
        "posts": conn.execute("SELECT COUNT(*) as n FROM posts").fetchone()["n"],
        "tmis": conn.execute("SELECT COUNT(*) as n FROM tmis").fetchone()["n"],
        "schedules": conn.execute("SELECT COUNT(*) as n FROM schedules").fetchone()["n"],
        "counselings": conn.execute("SELECT COUNT(*) as n FROM counselings").fetchone()["n"],
    }


# ── 增删改 ──────────────────────────────────────

def add_tmi(idol_id: int, content: str, category: str, confidence: str = "medium",
            quote: str = "", post_id: int = None, post_url: str = "",
            post_date: str = "", post_likes: int = 0) -> int:
    """手动添加一条 TMI"""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO tmis (idol_id, content, category, confidence, quote, post_id, post_url, post_date, post_likes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (idol_id, content, category, confidence, quote, post_id, post_url, post_date, post_likes))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_tmi(tmi_id: int, **kwargs):
    """更新 TMI 的任意字段，如 update_tmi(3, content='新内容', confidence='high')"""
    allowed = {"content", "category", "confidence", "quote"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE tmis SET {sets} WHERE id = ?", list(updates.values()) + [tmi_id])
    conn.commit()
    conn.close()


def delete_tmi(tmi_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM tmis WHERE id = ?", (tmi_id,))
    conn.commit()
    conn.close()


def update_idol(idol_id: int, **kwargs):
    """更新 idol 信息"""
    allowed = {"name", "group_name", "birthday", "avatar_url", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE idols SET {sets} WHERE id = ?", list(updates.values()) + [idol_id])
    conn.commit()
    conn.close()


def add_schedule(idol_id: int, title: str, event_type: str = "其他",
                 start_date: str = "", end_date: str = "", location: str = "",
                 description: str = "", source_url: str = "",
                 source_post_id: int = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO schedules (idol_id, title, event_type, start_date, end_date, location, description, source_post_id, source_url)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (idol_id, title, event_type, start_date, end_date, location, description, source_post_id, source_url))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_schedule(sched_id: int, **kwargs):
    allowed = {"title", "event_type", "start_date", "end_date", "location", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE schedules SET {sets} WHERE id = ?", list(updates.values()) + [sched_id])
    conn.commit()
    conn.close()


def delete_schedule(sched_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM schedules WHERE id = ?", (sched_id,))
    conn.commit()
    conn.close()


def get_schedules(idol_id: int, event_type: str = None) -> list[dict]:
    """获取行程列表"""
    conn = get_connection()
    if event_type:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE idol_id = ? AND event_type = ? ORDER BY start_date DESC",
            (idol_id, event_type)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE idol_id = ? ORDER BY start_date DESC",
            (idol_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── 烦恼商谈 ────────────────────────────────────

def insert_counselings(conn: sqlite3.Connection, items: list[dict], idol_id: int):
    cur = conn.executemany("""
        INSERT INTO counselings (idol_id, content, quote, post_id, post_url, post_date, post_likes)
        VALUES (?,?,?,?,?,?,?)
    """, [
        (
            idol_id, c["content"], c.get("quote", ""), c.get("post_id"),
            c.get("post_url", ""), c.get("post_date", ""), c.get("post_likes", 0)
        )
        for c in items
    ])
    return cur.rowcount


def get_counselings(idol_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM counselings WHERE idol_id = ? ORDER BY post_date DESC",
        (idol_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_counseling(keyword: str, idol_id: int = None, limit: int = 20) -> list[dict]:
    conn = get_connection()
    pattern = f"%{keyword}%"
    conditions = ["(content LIKE ? OR quote LIKE ?)"]
    params = [pattern, pattern]
    if idol_id:
        conditions.append("idol_id = ?")
        params.append(idol_id)
    sql = f"""
        SELECT c.*, i.name as idol_name FROM counselings c
        JOIN idols i ON c.idol_id = i.id
        WHERE {' AND '.join(conditions)}
        ORDER BY c.post_date DESC LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_counseling(idol_id: int, content: str, quote: str = "",
                   post_id: int = None, post_url: str = "",
                   post_date: str = "", post_likes: int = 0) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO counselings (idol_id, content, quote, post_id, post_url, post_date, post_likes)
           VALUES (?,?,?,?,?,?,?)""",
        (idol_id, content, quote, post_id, post_url, post_date, post_likes))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_counseling(counseling_id: int, **kwargs):
    allowed = {"content", "quote"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE counselings SET {sets} WHERE id = ?", list(updates.values()) + [counseling_id])
    conn.commit()
    conn.close()


def delete_counseling(counseling_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM counselings WHERE id = ?", (counseling_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    stats = get_db_stats()
    print(f"统计：{stats['idols']} 位偶像, {stats['posts']} 条帖子, "
          f"{stats['tmis']} 条TMI, {stats['schedules']} 条行程")
