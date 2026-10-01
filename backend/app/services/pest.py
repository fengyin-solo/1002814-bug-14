"""病虫害防治业务规则：等级重算、统一筛选与排序口径都收在这里。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "pest"
REQUIRED_FIELDS = ["防治编号", "受害植物", "病虫种类"]
STATUS_ORDER = ["待防治", "防治中", "已防治", "需复查"]
ACTION_RULES = {"安排防治": "防治中", "开始防治": "已防治", "安排复查": "需复查"}
NEGATIVE_ACTIONS = []

# 危害等级由重到轻；清单、导出、缺药剂清单共用这一份排序口径，
# 保证同一条记录在任何页面排到的位置都一致。
LEVEL_RANK = {"严重": 4, "重": 3, "中": 2, "轻": 1}
# 发生面积（亩）达到各等级的默认下限；判定标准调整时按新下限重算。
DEFAULT_THRESHOLDS = {"severe_at": 50.0, "heavy_at": 20.0, "medium_at": 5.0}
_AREA_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _level_rank(row: dict[str, Any]) -> int:
    return LEVEL_RANK.get(str(row.get("危害等级") or "").strip(), 0)


def _contains(row: dict[str, Any], field: str, needle: str) -> bool:
    """包含匹配，不去掉任何一条数据：大小写、首尾空白都不影响命中。"""
    return needle.strip().casefold() in str(row.get(field) or "").strip().casefold()


def _has_pesticide(row: dict[str, Any]) -> bool:
    return bool(str(row.get("防治药剂") or "").strip())


def _sorted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """危害等级高的排前面；同级再按防治编号、id 兜底，保证顺序稳定一致。"""
    return sorted(
        rows,
        key=lambda row: (
            -_level_rank(row),
            str(row.get("防治编号") or ""),
            int(row.get("id", 0)),
        ),
    )


class PestService:
    def query_entries(
        self,
        *,
        keyword: str | None = None,
        plant: str | None = None,
        species: str | None = None,
        status: str | None = None,
        level: str | None = None,
        pesticide_missing: bool = False,
    ) -> list[dict[str, Any]]:
        """按防治编号、受害植物、病虫种类等条件过滤并统一排序。

        列表分页、导出清单、缺药剂清单都走这一份口径，取到的永远是同一份数据。
        """
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if _contains(row, "防治编号", keyword)]
        if plant:
            rows = [row for row in rows if _contains(row, "受害植物", plant)]
        if species:
            rows = [row for row in rows if _contains(row, "病虫种类", species)]
        if level:
            rows = [row for row in rows if str(row.get("危害等级") or "").strip() == level]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if pesticide_missing:
            rows = [row for row in rows if not _has_pesticide(row)]
        return _sorted(rows)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        plant: str | None = None,
        species: str | None = None,
        status: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self.query_entries(
            keyword=keyword, plant=plant, species=species, status=status, level=level
        )
        total = len(rows)
        page = max(page, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def list_missing_pesticide(
        self,
        *,
        keyword: str | None = None,
        plant: str | None = None,
        species: str | None = None,
        status: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """缺防治药剂的记录单独取一份，不混在分页里，翻页也不会丢。"""
        rows = self.query_entries(
            keyword=keyword,
            plant=plant,
            species=species,
            status=status,
            level=level,
            pesticide_missing=True,
        )
        total = len(rows)
        page = max(page, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def recompute_levels(self, values: dict[str, Any] | None = None) -> tuple[int, int]:
        """按最新的发生面积判定标准，把已有记录的危害等级全部重算一遍。

        返回 (实际更新条数, 面积无法识别而跳过的条数)。
        """
        values = values or {}
        try:
            severe_at = float(values.get("severe_at", DEFAULT_THRESHOLDS["severe_at"]))
            heavy_at = float(values.get("heavy_at", DEFAULT_THRESHOLDS["heavy_at"]))
            medium_at = float(values.get("medium_at", DEFAULT_THRESHOLDS["medium_at"]))
        except (TypeError, ValueError):
            raise ValueError("危害等级面积下限必须是数字")
        if not severe_at > heavy_at > medium_at > 0:
            raise ValueError("面积下限需满足 严重 > 重 > 中 > 0，请检查判定标准")

        updated = 0
        skipped = 0
        for row in store.rows(MODULE):
            match = _AREA_PATTERN.search(str(row.get("发生面积") or ""))
            if not match:
                skipped += 1
                continue
            area = float(match.group())
            if area >= severe_at:
                new_level = "严重"
            elif area >= heavy_at:
                new_level = "重"
            elif area >= medium_at:
                new_level = "中"
            elif area > 0:
                new_level = "轻"
            else:
                skipped += 1
                continue
            if str(row.get("危害等级") or "").strip() != new_level:
                row["危害等级"] = new_level
                updated += 1
        return updated, skipped

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防治记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于病虫害防治可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"防治记录已{action}"
