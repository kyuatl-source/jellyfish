"""
追星助手 · FastAPI 后端
启动：python server.py
访问：http://localhost:8765
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import (
    init_db, get_db_stats, get_connection,
    search_tmi, get_idol_tmis, get_tmi_categories, get_schedules,
    add_tmi, update_tmi, delete_tmi,
    add_schedule, update_schedule, delete_schedule,
    update_idol,
    get_counselings, search_counseling,
    add_counseling, update_counseling, delete_counseling,
    get_tmi_tags, save_tmi_tags,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="追星助手 API", version="0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 模型定义 ──
class TmiCreate(BaseModel):
    idol_id: int
    content: str
    category: str
    categories: str | None = None
    confidence: str = "medium"
    quote: str = ""
    post_id: int | None = None
    post_url: str = ""
    post_date: str = ""
    post_likes: int = 0


class TmiUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    categories: str | None = None
    confidence: str | None = None
    quote: str | None = None


class ScheduleCreate(BaseModel):
    idol_id: int
    title: str
    event_type: str = "其他"
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    description: str = ""
    source_url: str = ""
    source_post_id: int | None = None


class ScheduleUpdate(BaseModel):
    title: str | None = None
    event_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    description: str | None = None


class IdolUpdate(BaseModel):
    name: str | None = None
    group_name: str | None = None
    birthday: str | None = None
    notes: str | None = None


class CounselingCreate(BaseModel):
    idol_id: int
    content: str
    quote: str = ""
    post_id: int | None = None
    post_url: str = ""
    post_date: str = ""
    post_likes: int = 0


class CounselingUpdate(BaseModel):
    content: str | None = None
    quote: str | None = None


class TmiTag(BaseModel):
    name: str
    color: str


class TmiTagsUpdate(BaseModel):
    tags: list[TmiTag]
    oldTags: list[TmiTag] | None = None


# ── 首页 ──
@app.get("/")
def index():
    return FileResponse("static/index.html")


# ── 统计概览 ──
@app.get("/api/stats")
def stats():
    return get_db_stats()


# ── Idol 相关 ──
@app.get("/api/idols/{idol_id}")
def get_idol(idol_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM idols WHERE id = ?", (idol_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Idol 不存在")
    return dict(row)


@app.put("/api/idols/{idol_id}")
def put_idol(idol_id: int, body: IdolUpdate):
    kwargs = body.model_dump(exclude_none=True)
    if kwargs:
        update_idol(idol_id, **kwargs)
    return {"ok": True}


# ── TMI 相关 ──
@app.get("/api/tmis/categories")
def categories(idol_id: int = Query(1)):
    return get_tmi_categories(idol_id)


@app.get("/api/tmis")
def list_tmis(
    idol_id: int = Query(1),
    category: str | None = Query(None),
    confidence: str | None = Query(None),
):
    return get_idol_tmis(idol_id, category=category, confidence=confidence)


@app.get("/api/tmis/search")
def search(q: str = Query(..., min_length=1), category: str | None = Query(None)):
    return search_tmi(q, category=category)


@app.post("/api/tmis")
def create_tmi(body: TmiCreate):
    tid = add_tmi(
        body.idol_id, body.content, body.category,
        confidence=body.confidence, quote=body.quote,
        post_id=body.post_id, post_url=body.post_url,
        post_date=body.post_date, post_likes=body.post_likes,
        categories=body.categories,
    )
    return {"ok": True, "id": tid}


@app.put("/api/tmis/{tmi_id}")
def put_tmi(tmi_id: int, body: TmiUpdate):
    kwargs = body.model_dump(exclude_none=True)
    if kwargs:
        update_tmi(tmi_id, **kwargs)
    return {"ok": True}


@app.delete("/api/tmis/{tmi_id}")
def remove_tmi(tmi_id: int):
    delete_tmi(tmi_id)
    return {"ok": True}


# ── 标签管理 ──

@app.get("/api/tmi-tags")
def list_tmi_tags():
    tags = get_tmi_tags()
    return {"tags": tags}


@app.put("/api/tmi-tags")
def save_tmi_tags_endpoint(body: TmiTagsUpdate):
    old = [t.model_dump() for t in body.oldTags] if body.oldTags else None
    save_tmi_tags([t.model_dump() for t in body.tags], old)
    return {"ok": True}


# ── 行程相关 ──
@app.get("/api/schedules")
def list_schedules(idol_id: int = Query(1)):
    return get_schedules(idol_id)


@app.post("/api/schedules")
def create_schedule(body: ScheduleCreate):
    sid = add_schedule(
        body.idol_id, body.title, body.event_type,
        start_date=body.start_date, end_date=body.end_date,
        location=body.location, description=body.description,
        source_url=body.source_url, source_post_id=body.source_post_id,
    )
    return {"ok": True, "id": sid}


@app.put("/api/schedules/{sched_id}")
def put_schedule(sched_id: int, body: ScheduleUpdate):
    kwargs = body.model_dump(exclude_none=True)
    if kwargs:
        update_schedule(sched_id, **kwargs)
    return {"ok": True}


@app.delete("/api/schedules/{sched_id}")
def remove_schedule(sched_id: int):
    delete_schedule(sched_id)
    return {"ok": True}


# ── 烦恼商谈 ──
@app.get("/api/counselings")
def list_counselings(idol_id: int = Query(1)):
    return get_counselings(idol_id)


@app.get("/api/counselings/search")
def search_counselings(q: str = Query(..., min_length=1)):
    return search_counseling(q)


@app.post("/api/counselings")
def create_counseling(body: CounselingCreate):
    cid = add_counseling(
        body.idol_id, body.content, quote=body.quote,
        post_id=body.post_id, post_url=body.post_url,
        post_date=body.post_date, post_likes=body.post_likes,
    )
    return {"ok": True, "id": cid}


@app.put("/api/counselings/{counseling_id}")
def put_counseling(counseling_id: int, body: CounselingUpdate):
    kwargs = body.model_dump(exclude_none=True)
    if kwargs:
        update_counseling(counseling_id, **kwargs)
    return {"ok": True}


@app.delete("/api/counselings/{counseling_id}")
def remove_counseling(counseling_id: int):
    delete_counseling(counseling_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
