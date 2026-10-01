"""园林绿化养护管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.routers.pest import service as pest_service
from app.store import store

app = FastAPI(title="园林绿化养护管理平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    病虫害防治的今日新增条数与防治清单共用 PestService 的同一份取数口径，
    看板上看到的条数和防治页查出来的始终对得上。
    """
    data = store.overview()
    for module in data["modules"]:
        if module["name"] == "pest":
            module["created"] = pest_service.count_entries()
    cards = data["cards"]
    for card in cards:
        if card["label"] == "今日新增":
            card["value"] = sum(int(item["created"]) for item in data["modules"])
    return data
