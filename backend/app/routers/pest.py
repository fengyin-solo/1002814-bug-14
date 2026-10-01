"""病虫害防治接口：维护防治记录，覆盖查询、导出、等级重算、状态流转等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.pest import LEVEL_RANK, PestService

router = APIRouter(prefix="/api/pest", tags=["病虫害防治"])

service = PestService()

LIST_FIELDS = ["防治编号", "受害植物", "病虫种类", "危害等级", "发生面积", "防治药剂", "防治日期", "防治状态"]
STATUSES = ["待防治", "防治中", "已防治", "需复查"]


def _service_kwargs(
    keyword: str | None,
    plant: str | None,
    species: str | None,
    status: str | None,
    level: str | None,
) -> dict[str, Any]:
    """把查询参数收口成一份，列表、导出、缺药剂清单都用它，保证同条件同结果。"""
    return {
        "keyword": keyword or None,
        "plant": plant or None,
        "species": species or None,
        "status": status or None,
        "level": level or None,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按防治编号检索"),
    plant: str | None = Query(default=None, description="按受害植物检索，包含即命中"),
    species: str | None = Query(default=None, description="按病虫种类检索，包含即命中"),
    status: str | None = Query(default=None, description="待防治、防治中、已防治、需复查"),
    level: str | None = Query(default=None, description="危害等级：严重、重、中、轻"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1),
) -> PageResult[dict]:
    """按防治编号、受害植物、病虫种类与状态过滤防治列表，按危害等级倒序排列。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if level and level not in LEVEL_RANK:
        raise HTTPException(status_code=400, detail="危害等级只支持：严重、重、中、轻")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="防治状态只支持：待防治、防治中、已防治、需复查")
    items, total = service.list_entries(
        **_service_kwargs(keyword, plant, species, status, level), page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/missing-pesticide", response_model=PageResult[dict])
def list_missing_pesticide(
    keyword: str | None = Query(default=None, description="按防治编号检索"),
    plant: str | None = Query(default=None, description="按受害植物检索"),
    species: str | None = Query(default=None, description="按病虫种类检索"),
    status: str | None = Query(default=None, description="待防治、防治中、已防治、需复查"),
    level: str | None = Query(default=None, description="危害等级：严重、重、中、轻"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1),
) -> PageResult[dict]:
    """缺防治药剂的记录单独成清单：不会因为翻页或漏填药剂而丢掉整行。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_missing_pesticide(
        **_service_kwargs(keyword, plant, species, status, level), page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/recompute-levels", response_model=ActionResult)
def recompute_levels(payload: EntryPayload | None = None) -> ActionResult:
    """危害等级判定标准调整后，按新标准把已有记录的危害等级重算一遍。"""
    values = (payload.values if payload is not None else None) or {}
    try:
        updated, skipped = service.recompute_levels(values)
    except ValueError as exc:
        return ActionResult(ok=False, message=str(exc))
    message = f"已按最新判定标准重算，{updated} 条记录危害等级更新"
    if skipped:
        message += f"，{skipped} 条因发生面积无法识别而跳过"
    return ActionResult(ok=True, message=message)


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    plant: str | None = None,
    species: str | None = None,
    status: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    """导出病虫害防治清单：沿用列表的同一套过滤与排序，条数与列表完全一致。"""
    items = service.query_entries(**_service_kwargs(keyword, plant, species, status, level))
    return {"module": "pest", "total": len(items), "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条防治记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"防治记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条防治记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防治记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条防治记录执行安排防治、开始防治、安排复查；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
