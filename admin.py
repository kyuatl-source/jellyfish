"""
追星助手 · 后台管理控制台
用法：python admin.py
"""
import os
from database import (
    init_db, get_db_stats, get_connection,
    search_tmi, get_idol_tmis, get_tmi_categories, get_schedules,
    add_tmi, update_tmi, delete_tmi,
    add_schedule, update_schedule, delete_schedule,
    update_idol,
)

IDOL_ID = 1  # 韩志薰


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def menu():
    clear()
    stats = get_db_stats()
    print("=" * 45)
    print(f"  追星助手 · 后台管理")
    print(f"  已录入：{stats['idols']}位idol | "
          f"{stats['posts']}条帖子 | "
          f"{stats['tmis']}条TMI | "
          f"{stats['schedules']}条行程")
    print("=" * 45)
    print("  [1] 查看 TMI（按分类）")
    print("  [2] 搜索 TMI")
    print("  [3] 添加 TMI")
    print("  [4] 修改 TMI")
    print("  [5] 删除 TMI")
    print("  [6] 查看行程")
    print("  [7] 添加行程")
    print("  [8] 修改行程")
    print("  [9] 删除行程")
    print("  [A] 查看/修改 Idol 信息")
    print("  [0] 退出")
    print("-" * 45)

    return input("  输入选项 → ").strip()


def show_tmis():
    cats = get_tmi_categories(IDOL_ID)
    print("\n  TMI 分类分布：")
    for c in cats:
        print(f"    {c['category']} ({c['cnt']}条)")

    cat = input("\n  输入分类名（留空=全部）→ ").strip()
    conf = input("  可信度 high/medium/low（留空=全部）→ ").strip()

    tmis = get_idol_tmis(IDOL_ID, category=cat or None, confidence=conf or None)
    print(f"\n  共 {len(tmis)} 条：")
    for t in tmis:
        print(f"  [{t['id']}] [{t['confidence']}] [{t['category']}] {t['content']}")
    input("\n  按回车返回...")


def search():
    kw = input("\n  搜索关键词 → ").strip()
    results = search_tmi(kw)
    print(f"\n  找到 {len(results)} 条：")
    for t in results:
        print(f"  [{t['id']}] [{t['category']}] {t['content']}")
        print(f"     原文引用：{t['quote']}")
    input("\n  按回车返回...")


def add_tmi_flow():
    print("\n  添加 TMI →")
    content = input("  TMI 内容 → ").strip()
    cat = input("  分类（饮食偏好/性格习惯/兴趣爱好/人际关系/成长经历/语言能力/身体小细节/恐惧与反应/价值观念/日常碎片）→ ").strip()
    conf = input("  可信度（high/medium/low）→ ").strip() or "medium"
    quote = input("  原文引用（可选）→ ").strip()
    tid = add_tmi(IDOL_ID, content, cat, confidence=conf, quote=quote)
    print(f"  已添加 TMI id={tid}")
    input("\n  按回车返回...")


def edit_tmi_flow():
    tid = input("\n  要修改的 TMI id → ").strip()
    if not tid.isdigit():
        return
    conn = get_connection()
    row = conn.execute("SELECT * FROM tmis WHERE id = ?", (int(tid),)).fetchone()
    if not row:
        print("  未找到")
        input("\n  按回车返回...")
        return
    t = dict(row)
    print(f"\n  当前: [{t['category']}] {t['content']}")
    print(f"  可信度={t['confidence']}  quote={t['quote']}")
    print("\n  输入新值（留空=不修改）：")

    content = input("  新内容 → ").strip()
    cat = input("  新分类 → ").strip()
    conf = input("  新可信度 → ").strip()
    quote = input("  新引用 → ").strip()

    kwargs = {}
    if content:
        kwargs["content"] = content
    if cat:
        kwargs["category"] = cat
    if conf:
        kwargs["confidence"] = conf
    if quote:
        kwargs["quote"] = quote

    if kwargs:
        update_tmi(int(tid), **kwargs)
        print("  已更新")
    else:
        print("  无修改")
    conn.close()
    input("\n  按回车返回...")


def delete_tmi_flow():
    tid = input("\n  要删除的 TMI id → ").strip()
    if tid.isdigit():
        delete_tmi(int(tid))
        print(f"  已删除 TMI id={tid}")
    input("\n  按回车返回...")


def show_schedules():
    scheds = get_schedules(IDOL_ID)
    print(f"\n  共 {len(scheds)} 条行程：")
    for s in scheds:
        print(f"  [{s['id']}] [{s['event_type']}] {s['title']}")
        print(f"      时间: {s.get('start_date','')} ~ {s.get('end_date','')}  地点: {s.get('location','')}")
    input("\n  按回车返回...")


def add_schedule_flow():
    print("\n  添加行程 →")
    title = input("  标题 → ").strip()
    etype = input("  类型（音乐回归/巡演/综艺/品牌活动/生日/其他）→ ").strip() or "其他"
    start = input("  开始日期(YYYY-MM-DD) → ").strip()
    end = input("  结束日期(YYYY-MM-DD，可选) → ").strip()
    loc = input("  地点（可选）→ ").strip()
    desc = input("  描述（可选）→ ").strip()
    sid = add_schedule(IDOL_ID, title, etype, start_date=start, end_date=end, location=loc, description=desc)
    print(f"  已添加行程 id={sid}")
    input("\n  按回车返回...")


def edit_schedule_flow():
    sid = input("\n  要修改的行程 id → ").strip()
    if not sid.isdigit():
        return
    conn = get_connection()
    row = conn.execute("SELECT * FROM schedules WHERE id = ?", (int(sid),)).fetchone()
    if not row:
        print("  未找到"); input("\n  按回车返回..."); return
    s = dict(row)
    print(f"\n  当前: [{s['event_type']}] {s['title']}")
    print(f"  时间: {s.get('start_date','')} ~ {s.get('end_date','')}")
    print("\n  输入新值（留空=不修改）：")
    title = input("  新标题 → ").strip()
    etype = input("  新类型 → ").strip()
    start = input("  新开始日期 → ").strip()
    end = input("  新结束日期 → ").strip()
    loc = input("  新地点 → ").strip()
    desc = input("  新描述 → ").strip()
    kwargs = {}
    for k, v in [("title", title), ("event_type", etype), ("start_date", start),
                 ("end_date", end), ("location", loc), ("description", desc)]:
        if v:
            kwargs[k] = v
    if kwargs:
        update_schedule(int(sid), **kwargs)
        print("  已更新")
    conn.close()
    input("\n  按回车返回...")


def edit_idol_flow():
    conn = get_connection()
    row = conn.execute("SELECT * FROM idols WHERE id = ?", (IDOL_ID,)).fetchone()
    if not row:
        print("  未找到idol"); input("\n  按回车返回..."); conn.close(); return
    i = dict(row)
    print(f"\n  当前 Idol 信息：")
    print(f"  名字: {i.get('name','')}")
    print(f"  所属团: {i.get('group_name','')}")
    print(f"  微博UID: {i.get('weibo_uid','')}")
    print(f"  生日: {i.get('birthday','')}")
    print(f"  备注: {i.get('notes','')}")
    print("\n  输入新值（留空=不修改）：")
    name = input("  新名字 → ").strip()
    group = input("  新团名 → ").strip()
    birthday = input("  新生日(YYYY-MM-DD) → ").strip()
    notes = input("  新备注 → ").strip()
    kwargs = {}
    for k, v in [("name", name), ("group_name", group), ("birthday", birthday), ("notes", notes)]:
        if v:
            kwargs[k] = v
    if kwargs:
        update_idol(IDOL_ID, **kwargs)
        print("  已更新")
    else:
        print("  无修改")
    conn.close()
    input("\n  按回车返回...")


def delete_schedule_flow():
    sid = input("\n  要删除的行程 id → ").strip()
    if sid.isdigit():
        delete_schedule(int(sid))
        print(f"  已删除行程 id={sid}")
    input("\n  按回车返回...")


def main():
    init_db()
    routes = {
        "1": show_tmis,
        "2": search,
        "3": add_tmi_flow,
        "4": edit_tmi_flow,
        "5": delete_tmi_flow,
        "6": show_schedules,
        "7": add_schedule_flow,
        "8": edit_schedule_flow,
        "9": delete_schedule_flow,
        "A": edit_idol_flow,
        "a": edit_idol_flow,
    }
    while True:
        choice = menu()
        if choice == "0":
            print("  再见~")
            break
        action = routes.get(choice)
        if action:
            action()
        else:
            input("  无效选项，按回车返回...")


if __name__ == "__main__":
    main()
