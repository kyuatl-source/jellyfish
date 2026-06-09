"""
导入爬取数据到数据库（支持增量）
用法：python import_data.py
"""
import json
from database import init_db, get_connection, ensure_idol, insert_posts, insert_tmis, get_db_stats

UID = "7730426245"
IDOL_NAME = "韩志薰"
IDOL_GROUP = "TWS"
POSTS_FILE = "weibo_posts.json"
TMI_FILE = "tmi_results.json"


def import_posts_incremental(conn, posts, idol_id):
    """增量导入帖子：只插入数据库中不存在的"""
    existing = {r[0] for r in conn.execute("SELECT id FROM posts").fetchall()}
    new = [p for p in posts if p["id"] not in existing]
    if new:
        n = insert_posts(conn, new, idol_id)
        print(f"帖子：新增 {n} 条（共 {len(posts)} 条，跳过 {len(posts)-len(new)} 条已存在）")
    else:
        print(f"帖子：全部 {len(posts)} 条均已存在，跳过")
    return len(new)


def main():
    init_db()
    conn = get_connection()

    # 1. 创建/获取 idol
    idol_id = ensure_idol(conn, name=IDOL_NAME, weibo_uid=UID, group_name=IDOL_GROUP)
    print(f"Idol: {IDOL_NAME} (id={idol_id})")

    # 2. 导入帖子（增量）
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)
    import_posts_incremental(conn, posts, idol_id)

    # 3. 导入 TMI
    try:
        with open(TMI_FILE, "r", encoding="utf-8") as f:
            tmis = json.load(f)
        n2 = insert_tmis(conn, tmis, idol_id)
        print(f"TMI：导入 {n2} 条（共 {len(tmis)} 条）")
    except FileNotFoundError:
        print("TMI 文件不存在，跳过")

    conn.commit()
    conn.close()

    # 4. 统计
    stats = get_db_stats()
    print(f"\n数据库概况：{stats['idols']} 位偶像, {stats['posts']} 条帖子, "
          f"{stats['tmis']} 条TMI, {stats['schedules']} 条行程")


if __name__ == "__main__":
    main()
