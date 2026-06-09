"""
微博主页爬取脚本
目标：https://weibo.com/u/7730426245
用法：
  python weibo_scraper.py           # 全量抓取
  python weibo_scraper.py --new     # 增量模式：只抓新帖，遇到数据库中已有帖子即停
输出：weibo_posts.json（所有帖子）+ weibo_posts.csv（便于查看）

说明：使用 weibo.com 桌面端 AJAX 接口，需要登录 Cookie。
"""

import requests
import json
import csv
import time
import re
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# ── 配置 ──────────────────────────────────────────
UID = "7730426245"
MAX_PAGES = 100            # 增量模式最多抓 100 页
DELAY = 1.5                # 每页间隔（秒）
STOP_BEFORE = "2024-01-01" # 抓到此日期之前的帖子时停止（全量模式用）
OUTPUT_JSON = "weibo_posts.json"
OUTPUT_CSV  = "weibo_posts.csv"
CHECKPOINT  = "weibo_checkpoint.json"  # 断点续传
SAVE_EVERY   = 10          # 每 N 页保存一次
DB_PATH = Path(__file__).parent / "star_tracker.db"
INCREMENTAL = "--new" in sys.argv  # 增量模式
# ──────────────────────────────────────────────────

COOKIE = "SINAGLOBAL=3334470387973.2407.1779180366111; SCF=AsUuX1Qi0uuGj0P1srWQLKD7dMMubEVPYNQ9HmDokMPBgvCN8m8zTsKYemas7Jhqg-_dCFAlZMlnRwDmu01FJVc.; ULV=1779774094487:2:2:2:96492876095.89386.1779774094487:1779180366112; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WW78KRbSTBgeWRCXEpU47Fv5JpX5KMhUgL.FoMNe05XeoqESh-2dJLoIEBLxKBLBonLBKBLxK-L1h-L1heLxKBLB.2L1KBLxKBLBonLB-2t; XSRF-TOKEN=kMmVqyt_GItcPtUCNrgp2en-; ALF=1783052333; SUB=_2A25HG9t9DeRhGeFJ6FIV8ijOzzmIHXVkWVK1rDV8PUJbkNANLXf4kW1NfFRXX07gjz8y3rRwfnYF-gaaCrlA8KDg; WBPSESS=Nv5h_w-bjXhp8H9z4CzshpYtIbKW7Aa_aIFB4-1urGQnMvp4SaCxSJ4OpGbZWkHxAUYrDRlJll00G0me311i_lIMwGyTJ5aV3Epofs1COsaUX_Xfdr_qa3qTJlKmIMeBd6uNJFID8jWlwiN1nc6BUQ=="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": f"https://weibo.com/u/{UID}",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "X-XSRF-TOKEN": "kMmVqyt_GItcPtUCNrgp2en-",
    "Cookie": COOKIE,
}

API_URL = "https://weibo.com/ajax/statuses/mymblog"


def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return text.strip()


def fetch_page(uid, page):
    params = {"uid": uid, "page": page, "feature": 0}
    try:
        resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok") == 0 and data.get("data"):
            return data
        if data.get("http_code") == 404 or data.get("ok") == 0:
            return None
        return data
    except requests.RequestException as e:
        print(f"  [错误] 第{page}页请求失败: {e}")
        return None


def parse_posts(data, uid):
    posts = []
    for item in data.get("data", {}).get("list", []):
        is_retweet = "retweeted_status" in item
        original = item.get("retweeted_status", {}) if is_retweet else item

        # 图片
        pic_num = item.get("pic_num", 0)

        # 用 text_raw（纯文本）或 text（HTML）
        text = item.get("text_raw", "") or clean_html(item.get("text", ""))

        posts.append({
            "id":           item.get("id", ""),
            "mid":          item.get("mid", ""),
            "created_at":   item.get("created_at", ""),
            "text":         text,
            "is_retweet":   is_retweet,
            "original_text": original.get("text_raw", "") or clean_html(original.get("text", "")) if is_retweet else "",
            "reposts":      item.get("reposts_count", 0),
            "comments":     item.get("comments_count", 0),
            "likes":        item.get("attitudes_count", 0),
            "pics":         pic_num,
            "url":          f"https://weibo.com/{uid}/{item.get('mid', '')}",
        })
    return posts


def save_json(posts, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"  → JSON 已保存：{path}")


def save_csv(posts, path):
    if not posts:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=posts[0].keys())
        writer.writeheader()
        writer.writerows(posts)
    print(f"  → CSV  已保存：{path}")


def get_existing_post_ids():
    """从数据库获取已导入的帖子 ID 集合（增量模式用）"""
    if not DB_PATH.exists():
        return set()
    conn = sqlite3.connect(str(DB_PATH))
    ids = {r[0] for r in conn.execute("SELECT id FROM posts").fetchall()}
    conn.close()
    return ids


def load_checkpoint():
    """加载断点数据，返回 (all_posts, seen_ids, last_page)"""
    import os
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            cp = json.load(f)
        seen = set(cp.get("seen_ids", []))
        print(f"发现断点：已抓 {cp['last_page']} 页，{len(cp['posts'])} 条，从第 {cp['last_page'] + 1} 页续抓\n")
        return cp["posts"], seen, cp["last_page"]
    return [], set(), 0


def save_checkpoint(posts, seen_ids, page):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump({
            "posts": posts,
            "seen_ids": list(seen_ids),
            "last_page": page,
            "updated": datetime.now().isoformat(),
        }, f, ensure_ascii=False)


def main():
    mode = "增量" if INCREMENTAL else "全量"
    print(f"开始{mode}抓取 UID={UID} 的微博主页")
    print(f"最多 {MAX_PAGES} 页，间隔 {DELAY}s，每 {SAVE_EVERY} 页存档\n")

    # 增量模式：加载数据库中已有的帖子 ID
    db_existing_ids = set()
    if INCREMENTAL:
        db_existing_ids = get_existing_post_ids()
        print(f"数据库中已有 {len(db_existing_ids)} 条帖子，遇到已知帖子即停止\n")

    all_posts, seen_ids, start_page = load_checkpoint()
    # 已有数据但无 checkpoint 时，从已有 JSON 恢复
    if not all_posts and start_page == 0:
        import os
        if os.path.exists(OUTPUT_JSON):
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing:
                all_posts = existing
                seen_ids = {p["id"] for p in existing}
                print(f"从已有文件恢复：{len(all_posts)} 条帖子\n")

    for page in range(start_page + 1, MAX_PAGES + 1):
        print(f"[{page}/{MAX_PAGES}] 请求第 {page} 页...", end=" ")
        data = fetch_page(UID, page)

        if not data:
            print("无数据或已到末页，停止。")
            break

        posts = parse_posts(data, UID)

        # 增量模式：过滤已知帖子，仅当整页全是已知帖子时才停止
        if INCREMENTAL:
            new_on_page = [p for p in posts if p["id"] not in db_existing_ids]
            known_on_page = len(posts) - len(new_on_page)
            if known_on_page == len(posts) and known_on_page > 0:
                print(f"整页 {len(posts)} 条均为已知帖子，增量抓取完成！")
                break
            new_posts = new_on_page
            if known_on_page > 0:
                print(f"（本页 {known_on_page} 条已知，{len(new_on_page)} 条新增）", end=" ")
        else:
            new_posts = [p for p in posts if p["id"] not in seen_ids]

        if not new_posts:
            print("本页无新帖，继续下一页...")
            time.sleep(DELAY)
            continue

        # 检查日期截止（全量模式）
        if STOP_BEFORE and not INCREMENTAL:
            from datetime import datetime as dt
            cutoff_posts = []
            hit_boundary = False
            for p in new_posts:
                try:
                    post_date = dt.strptime(p["created_at"], "%a %b %d %H:%M:%S %z %Y")
                    if post_date.strftime("%Y-%m-%d") < STOP_BEFORE:
                        hit_boundary = True
                    else:
                        cutoff_posts.append(p)
                except ValueError:
                    cutoff_posts.append(p)
            if hit_boundary:
                for p in cutoff_posts:
                    seen_ids.add(p["id"])
                all_posts.extend(cutoff_posts)
                print(f"获得 {len(cutoff_posts)} 条，累计 {len(all_posts)} 条（触及 {STOP_BEFORE} 截止，停止）")
                break

        for p in new_posts:
            seen_ids.add(p["id"])
        all_posts.extend(new_posts)
        print(f"获得 {len(new_posts)} 条，累计 {len(all_posts)} 条")

        # 定期存档
        if page % SAVE_EVERY == 0:
            save_checkpoint(all_posts, seen_ids, page)
            save_json(all_posts, OUTPUT_JSON)
            save_csv(all_posts, OUTPUT_CSV)
            print(f"  💾 已存档（第 {page} 页）")

        time.sleep(DELAY)

    print(f"\n{mode}抓取完成，共 {len(all_posts)} 条帖子")
    save_json(all_posts, OUTPUT_JSON)
    save_csv(all_posts, OUTPUT_CSV)

    # 清理断点
    import os
    if os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)

    print("\n── 最新5条预览 ──")
    for p in all_posts[:5]:
        tag = "[转发]" if p["is_retweet"] else "[原创]"
        print(f"{tag} {p['created_at']}")
        print(f"  {p['text'][:80]}{'…' if len(p['text'])>80 else ''}")
        print(f"  👍{p['likes']}  💬{p['comments']}  🔁{p['reposts']}")
        print()


if __name__ == "__main__":
    main()
