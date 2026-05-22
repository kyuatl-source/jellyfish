"""
TMI 提取器 · 从数据库按赞筛选 + 分批提取 + 断点续传
用法：python tmi_extractor.py
"""
import json
import csv
import time
import os
import anthropic
from database import get_connection, insert_tmis
from collections import Counter

# ── 配置 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MIN_LIKES         = 100       # 最低赞数阈值
BATCH_SIZE        = 5         # 每批发给 AI 的帖子数
DELAY             = 1.0        # 批次间隔（秒）
IDOL_ID           = 1          # 数据库中的 idol id
OUTPUT_JSON       = "tmi_results.json"
OUTPUT_CSV        = "tmi_results.csv"
IDOL_NAME         = "韩志薰 (Jihoon, TWS成员)"
# ──────────────────────────────────────────────────

TMI_CATEGORIES = {
    "饮食偏好":   "最爱食物、忌口、零食、饮料、家乡口味等",
    "性格习惯":   "起床/睡眠习惯、整洁度、时间观念、社交风格等",
    "兴趣爱好":   "游戏、运动、追剧、音乐、收藏等课余爱好",
    "人际关系":   "成员/朋友互动、家人提及、前辈后辈关系等",
    "成长经历":   "学生时代、出道前故事、家乡记忆等",
    "语言能力":   "外语水平、口头禅、方言、说话习惯等",
    "身体小细节": "小动作、惯用手、身体特征、外貌细节等",
    "恐惧与反应": "怕什么、惊喜反应、应激反应等",
    "价值观念":   "人生观、对工作的态度、喜欢的事物类型等",
    "日常碎片":   "不属于以上分类的日常小细节",
}

SYSTEM_PROMPT = f"""你是一个专业的偶像信息整理助手。
你的任务是从微博帖子中提取关于 {IDOL_NAME} 的 TMI（Too Much Information，即粉丝感兴趣的个人小细节）。

TMI 的定义：偶像本人透露的个人习惯、喜好、经历、性格等具体细节。
不算 TMI 的内容：宣传活动、官方公告、转发他人内容、纯粹的感谢/打招呼。

分类体系（从中选择最合适的一个）：
{json.dumps(TMI_CATEGORIES, ensure_ascii=False, indent=2)}

输出格式（严格 JSON，不要输出任何其他内容）：
{{
  "tmi_list": [
    {{
      "content": "提取出的 TMI 内容（用自然语言描述，50字以内）",
      "category": "分类名称（必须是上面分类体系中的一个）",
      "confidence": "high/medium/low（high=本人明确说的，medium=可以合理推断，low=间接暗示）",
      "quote": "原文中支持该 TMI 的关键句子（直接引用，不超过30字）",
      "post_id": "该帖子的 id 字段值"
    }}
  ],
  "skipped_count": 无 TMI 的帖子数量
}}

注意：
- 一条帖子可能含多条 TMI，也可能一条都没有
- 转发帖通常不含 idol 本人 TMI，跳过即可
- 如果整批帖子都没有 TMI，返回 {{"tmi_list": [], "skipped_count": N}}
"""


def load_posts_from_db(min_likes: int):
    """从数据库读取原创帖子，按赞数降序"""
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
    """获取数据库中已有 TMI 的 post_id 列表（用于断点续传）"""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT post_id FROM tmis").fetchall()
    conn.close()
    return {str(r["post_id"]) for r in rows if r["post_id"]}


def build_user_message(posts: list[dict]) -> str:
    lines = ["以下是需要分析的微博帖子，请提取其中的 TMI：\n"]
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


def extract_tmi_batch(client: anthropic.Anthropic, posts: list[dict]) -> list[dict]:
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
        return result.get("tmi_list", [])
    except json.JSONDecodeError as e:
        print(f"  [警告] JSON 解析失败: {e}")
        return []
    except anthropic.APIError as e:
        print(f"  [错误] API 调用失败: {e}")
        return []


def enrich_tmi(tmi_list: list[dict], posts: list[dict]) -> list[dict]:
    post_map = {str(p["id"]): p for p in posts}
    for tmi in tmi_list:
        post = post_map.get(str(tmi.get("post_id", "")), {})
        tmi["post_url"]    = post.get("url", "")
        tmi["post_date"]   = post.get("created_at", "")
        tmi["post_likes"]  = post.get("likes_count", 0)
    return tmi_list


def save_json(data: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  → JSON 已保存：{path}")


def save_csv(data: list[dict], path: str):
    if not data:
        return
    fields = ["category", "content", "confidence", "quote", "post_date", "post_url", "post_likes", "post_id"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"  → CSV  已保存：{path}")


def save_to_db(all_tmi: list[dict]):
    """把新增 TMI 入库，按 (post_id, content) 去重"""
    conn = get_connection()
    added = 0
    for t in all_tmi:
        exists = conn.execute(
            "SELECT id FROM tmis WHERE post_id = ? AND content = ?",
            (t.get("post_id"), t["content"])
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO tmis (idol_id, content, category, confidence, quote, post_id, post_url, post_date, post_likes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (IDOL_ID, t["content"], t["category"], t.get("confidence", "low"),
                 t.get("quote", ""), t.get("post_id"), t.get("post_url", ""),
                 t.get("post_date", ""), t.get("post_likes", 0))
            )
            added += 1
    conn.commit()
    conn.close()
    print(f"  → 入库 {added} 条新 TMI")


def print_summary(all_tmi: list[dict]):
    counts = Counter(t["category"] for t in all_tmi)
    high = sum(1 for t in all_tmi if t.get("confidence") == "high")
    print(f"\n{'─'*40}")
    print(f"✅ 本轮提取 TMI：{len(all_tmi)} 条（高可信度 {high} 条）")
    print("📂 分类分布：")
    for cat, count in counts.most_common():
        print(f"  {cat:<10} {'█' * count} {count}")
    print(f"\n📌 高可信度示例（最多3条）：")
    samples = [t for t in all_tmi if t.get("confidence") == "high"][:3]
    for t in samples:
        print(f"  [{t['category']}] {t['content']}")
        print(f"    原文：{t['quote']}")


def main():
    print("=" * 50)
    print("TMI 提取器 · 高赞帖子分批提取")
    print("=" * 50)

    if not ANTHROPIC_API_KEY:
        print("❌ 请设置 ANTHROPIC_API_KEY 环境变量")
        return

    # 1. 从数据库加载帖子
    posts = load_posts_from_db(MIN_LIKES)
    print(f"≥{MIN_LIKES}赞原创帖：{len(posts)} 条")

    # 2. 跳过已分析过的帖子（断点续传）
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

    # 3. 初始化客户端
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 4. 分批提取
    all_new_tmi = []
    total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"[{batch_num}/{total_batches}] 分析帖子 "
              f"(赞{min(p.get('likes_count',0) for p in batch)}~"
              f"{max(p.get('likes_count',0) for p in batch)})...",
              end=" ")

        tmi_batch = extract_tmi_batch(client, batch)
        tmi_batch = enrich_tmi(tmi_batch, batch)
        all_new_tmi.extend(tmi_batch)

        # 每批入库（防止中断丢失）
        if tmi_batch:
            save_to_db(tmi_batch)

        print(f"提取 {len(tmi_batch)} 条，累计 {len(all_new_tmi)} 条（本轮）")

        # 每 20 批存档一次 JSON/CSV
        if batch_num % 20 == 0:
            save_json(all_new_tmi, OUTPUT_JSON)
            save_csv(all_new_tmi, OUTPUT_CSV)

        time.sleep(DELAY)

    # 5. 最终保存
    print()
    save_json(all_new_tmi, OUTPUT_JSON)
    save_csv(all_new_tmi, OUTPUT_CSV)
    print_summary(all_new_tmi)


if __name__ == "__main__":
    main()
