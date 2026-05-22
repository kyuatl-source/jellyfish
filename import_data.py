"""
一次性导入已有数据到数据库
用法：python import_data.py
"""
import json
from database import init_db, get_connection, ensure_idol, insert_posts, insert_tmis, get_db_stats

UID = "7730426245"
IDOL_NAME = "韩志薰"
IDOL_GROUP = "TWS"
POSTS_FILE = "weibo_posts.json"
TMI_FILE = "tmi_results.json"


def main():
    init_db()
    conn = get_connection()

    # 1. 创建 idol
    idol_id = ensure_idol(conn, name=IDOL_NAME, weibo_uid=UID, group_name=IDOL_GROUP)
    print(f"Idol: {IDOL_NAME} (id={idol_id})")

    # 2. 导入帖子
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)
    n = insert_posts(conn, posts, idol_id)
    print(f"帖子：导入 {n} 条（共 {len(posts)} 条）")

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
