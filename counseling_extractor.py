"""
烦恼商谈提取器 · 从高赞帖子中提取 idol 给粉丝的安慰/建议/开导
用法：python counseling_extractor.py
"""
import json
import csv
import time
import os
import anthropic
from database import get_connection, insert_counselings

# ── 配置 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MIN_LIKES         = 0
BATCH_SIZE        = 5
DELAY             = 1.0
IDOL_ID           = 1
OUTPUT_JSON       = "counseling_results.json"
OUTPUT_CSV        = "counseling_results.csv"
IDOL_NAME         = "韩志薰 (Jihoon, TWS成员)"
# ──────────────────────────────────────────────────

SYSTEM_PROMPT = f"""你是一个专业的偶像信息整理助手。
你的任务是从微博帖子中提取关于 {IDOL_NAME} 的"烦恼商谈"内容。

"烦恼商谈"的定义：idol 对粉丝的安慰、建议、开导，或者 idol 谈论自己如何面对困难、压力、焦虑等话题的内容。

不算烦恼商谈的内容：
- 宣传活动、官方公告、转发他人内容
- 纯粹的感谢/打招呼/普通聊天
- idol 个人的 TMI（喜好、习惯等）

输出格式（严格 JSON，不要输出任何其他内容）：
{{
  "counseling_list": [
    {{
      "content": "提取出的烦恼商谈内容（用自然语言描述，80字以内）",
      "quote": "原文中支持该内容的关键句子（直接引用，不超过50字）",
      "post_id": "该帖子的 id 字段值"
    }}
  ],
  "skipped_count": 无烦恼商谈内容的帖子数量
}}

注意：
- 一条帖子可能含多条商谈内容，也可能一条都没有
- 如果整批帖子都没有烦恼商谈内容，返回 {{"counseling_list": [], "skipped_count": N}}
"""


def load_posts_from_db(min_likes: int):
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, mid, text, is_retweet, original_text, url, created_at,
                  likes_count, reposts_count, comments_count, pics_count
           FROM posts WHERE is_retweet = 0 AND likes_count >= ?
           ORDER BY likes_count DESC""",
        (min_likes,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analyzed_post_ids():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT post_id FROM counselings").fetchall()
    conn.close()
    return {str(r["post_id"]) for r in rows if r["post_id"]}


def build_user_message(posts: list[dict]) -> str:
    lines = ["以下是需要分析的微博帖子，请提取其中的烦恼商谈内容：\n"]
    for p in posts:
        lines.append(f"--- 帖子 id={p['id']} 时间={p['created_at']} ---")
        if p.get("is_retweet"):
            lines.append(f"[转发帖] 转发语：{p['text']}")
            if p.get("original_text"):
                lines.append(f"原文：{p['original_text']}")
        else:
            lines.append(p["text"])
        lines.append("")
    return "\n".join(lines)


def extract_counseling_batch(client: anthropic.Anthropic, posts: list[dict]) -> list[dict]:
    user_msg = build_user_message(posts)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text_blocks = [b for b in response.content if b.type == "text"]
        if not text_blocks:
            print("  [警告] 响应中无文本内容")
            return []
        raw = text_blocks[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        result = json.loads(raw)
        return result.get("counseling_list", [])
    except json.JSONDecodeError as e:
        print(f"  [警告] JSON 解析失败: {e}")
        return []
    except anthropic.APIError as e:
        print(f"  [错误] API 调用失败: {e}")
        return []


def enrich_counseling(items: list[dict], posts: list[dict]) -> list[dict]:
    post_map = {str(p["id"]): p for p in posts}
    for c in items:
        post = post_map.get(str(c.get("post_id", "")), {})
        c["post_url"]    = post.get("url", "")
        c["post_date"]   = post.get("created_at", "")
        c["post_likes"]  = post.get("likes_count", 0)
    return items


def save_json(data: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  → JSON 已保存：{path}")


def save_csv(data: list[dict], path: str):
    if not data:
        return
    fields = ["content", "quote", "post_date", "post_url", "post_likes", "post_id"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"  → CSV  已保存：{path}")


def save_to_db(all_items: list[dict]):
    conn = get_connection()
    added = 0
    for c in all_items:
        exists = conn.execute(
            "SELECT id FROM counselings WHERE post_id = ? AND content = ?",
            (c.get("post_id"), c["content"])
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO counselings (idol_id, content, quote, post_id, post_url, post_date, post_likes)
                   VALUES (?,?,?,?,?,?,?)""",
                (IDOL_ID, c["content"], c.get("quote", ""), c.get("post_id"),
                 c.get("post_url", ""), c.get("post_date", ""), c.get("post_likes", 0))
            )
            added += 1
    conn.commit()
    conn.close()
    print(f"  → 入库 {added} 条新商谈")


def print_summary(all_items: list[dict]):
    print(f"\n{'─'*40}")
    print(f"✅ 本轮提取烦恼商谈：{len(all_items)} 条")
    print(f"📌 示例（最多5条）：")
    for c in all_items[:5]:
        print(f"  {c['content']}")
        print(f"    原文：{c['quote']}")


def main():
    print("=" * 50)
    print("烦恼商谈提取器 · 高赞帖子分批提取")
    print("=" * 50)

    if not ANTHROPIC_API_KEY:
        print("❌ 请设置 ANTHROPIC_API_KEY 环境变量")
        return

    posts = load_posts_from_db(MIN_LIKES)
    print(f"≥{MIN_LIKES}赞原创帖：{len(posts)} 条")

    analyzed = get_analyzed_post_ids()
    remaining = [p for p in posts if str(p["id"]) not in analyzed]
    skipped = len(posts) - len(remaining)
    if skipped:
        print(f"已分析 {skipped} 条（断点续传），剩余 {len(remaining)} 条\n")
    else:
        print(f"开始分析 {len(remaining)} 条\n")

    if not remaining:
        print("✅ 所有帖子已分析完毕")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    all_new = []
    total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"[{batch_num}/{total_batches}] 分析帖子 "
              f"(赞{min(p.get('likes_count',0) for p in batch)}~"
              f"{max(p.get('likes_count',0) for p in batch)})...",
              end=" ")

        items = extract_counseling_batch(client, batch)
        items = enrich_counseling(items, batch)
        all_new.extend(items)

        if items:
            save_to_db(items)

        print(f"提取 {len(items)} 条，累计 {len(all_new)} 条（本轮）")

        if batch_num % 20 == 0:
            save_json(all_new, OUTPUT_JSON)
            save_csv(all_new, OUTPUT_CSV)

        time.sleep(DELAY)

    print()
    save_json(all_new, OUTPUT_JSON)
    save_csv(all_new, OUTPUT_CSV)
    print_summary(all_new)


if __name__ == "__main__":
    main()
