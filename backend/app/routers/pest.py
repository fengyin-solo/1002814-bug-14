"""病虫害防治接口：维护防治记录，覆盖安排防治、开始防治、安排复查等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.pest import PestService

router = APIRouter(prefix="/api/pest", tags=["病虫害防治"])

service = PestService()

LIST_FIELDS = ["防治编号", "受害植物", "病虫种类", "危害等级", "发生面积", "防治药剂", "防治日期", "防治状态"]
STATUSES = ["待防治", "防治中", "已防治", "需复查"]


def _list_kwargs(
    keyword: str | None,
    plant: str | None,
    species: str | None,
    status: str | None,
    missing_chemical: bool,
) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "plant": plant,
        "species": species,
        "status": status,
        "missing_chemical": missing_chemical,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按防治编号检索"),
    plant: str | None = Query(default=None, description="按受害植物名称包含检索"),
    species: str | None = Query(default=None, description="按病虫种类包含检索"),
    status: str | None = Query(default=None, description="待防治、防治中、已防治、需复查"),
    missing_chemical: bool = Query(default=False, description="只看未填防治药剂的记录"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按防治编号、受害植物、病虫种类与状态过滤；等级高的排前面，没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    page = max(page, 1)
    items, total = service.list_entries(
        **_list_kwargs(keyword, plant, species, status, missing_chemical),
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/count")
def count_entries(
    keyword: str | None = None,
    plant: str | None = None,
    species: str | None = None,
    status: str | None = None,
    missing_chemical: bool = False,
) -> dict[str, Any]:
    """与清单同一份筛选口径下的总条数，其他页面取数一律走这里，保证条数一致。"""
    total = service.count_entries(
        **_list_kwargs(keyword, plant, species, status, missing_chemical)
    )
    return {"total": total}


@router.get("/missing-chemical")
def list_missing_chemical(
    plant: str | None = Query(default=None, description="按受害植物名称包含检索"),
    species: str | None = Query(default=None, description="按病虫种类包含检索"),
) -> dict[str, Any]:
    """单独列出没填防治药剂的记录，方便统一补录，不再混在分页里被翻丢。"""
    items, total = service.missing_chemical_entries(plant=plant, species=species)
    return {"total": total, "items": items}


@router.get("/grade-rules")
def get_grade_rules() -> dict[str, Any]:
    """读取当前危害等级判定标准（重度 / 中度的发生面积阈值）。"""
    return service.grade_rules()


@router.put("/grade-rules", response_model=ActionResult)
def update_grade_rules(payload: EntryPayload) -> ActionResult:
    """调整危害等级判定标准，并对已有防治记录全部重算一遍。"""
    values = payload.values
    try:
        severe = float(values.get("severe_threshold"))
        moderate = float(values.get("moderate_threshold"))
    except (TypeError, ValueError):
        return ActionResult(ok=False, message="重度阈值与中度阈值都必须是数字，等级标准未更新")
    rules, message = service.update_grade_rules(severe, moderate)
    if rules is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=rules)


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    plant: str | None = None,
    species: str | None = None,
    status: str | None = None,
    missing_chemical: bool = False,
) -> dict[str, Any]:
    """导出病虫害防治清单：与页面同一份筛选、排序口径下的全量数据。"""
    items, total = service.list_entries(
        **_list_kwargs(keyword, plant, species, status, missing_chemical),
        page=1,
        size=10000,
    )
    return {"module": "pest", "total": total, "items": items}


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
