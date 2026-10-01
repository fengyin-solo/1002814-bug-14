"""病虫害防治业务规则：等级判定、状态流转、字段校验、筛选与统一排序都收在这里。

危害等级（重度/中度/轻度）按发生面积与当前等级标准实时判定；等级标准调整后会对已有
记录全部重算一遍，避免老记录一直挂着旧等级。清单、导出、缺药剂清单走同一个筛选与
排序入口，保证同一株受害植物在各处排的位置一致。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "pest"
REQUIRED_FIELDS = ["防治编号", "受害植物", "病虫种类"]
OPTIONAL_FIELDS = ["发生面积", "防治药剂", "防治日期"]
STATUS_ORDER = ["待防治", "防治中", "已防治", "需复查"]
ACTION_RULES = {"安排防治": "防治中", "开始防治": "已防治", "安排复查": "需复查"}
NEGATIVE_ACTIONS = []

# 危害等级从重到轻；未识别出等级的记录统一排到最后
GRADE_ORDER = ["重度", "中度", "轻度"]
DEFAULT_SEVERE_THRESHOLD = 50.0
DEFAULT_MODERATE_THRESHOLD = 20.0

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_text(value: Any) -> str:
    """把字段值转成可检索的文本；None / 空白都按空串处理，绝不让记录因此被丢掉。"""
    if value is None:
        return ""
    return str(value).strip()


def parse_area(value: Any) -> float | None:
    """从发生面积里取数值，兼容 ``35``、``35.5亩``、``约 12 ㎡`` 这类写法；取不到返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER_RE.search(str(value))
    return float(match.group()) if match else None


class PestService:
    def __init__(self) -> None:
        # 发生面积 >= 重度阈值判重度；否则 >= 中度阈值判中度；再否则判轻度
        self.severe_threshold = DEFAULT_SEVERE_THRESHOLD
        self.moderate_threshold = DEFAULT_MODERATE_THRESHOLD
        # 种子数据 / 已落库记录带进来的等级可能是按旧标准判的，启动时先重算一遍
        self.regrade_all()

    # ---- 等级判定与重算 -------------------------------------------------

    def grade_rules(self) -> dict[str, float]:
        return {
            "severe_threshold": self.severe_threshold,
            "moderate_threshold": self.moderate_threshold,
        }

    def classify(self, area: Any) -> str:
        """按当前等级标准判定一条记录的危害等级。"""
        value = parse_area(area)
        if value is None:
            return GRADE_ORDER[-1]
        if value >= self.severe_threshold:
            return GRADE_ORDER[0]
        if value >= self.moderate_threshold:
            return GRADE_ORDER[1]
        return GRADE_ORDER[2]

    def regrade_all(self) -> int:
        """按当前等级标准重算全部已有记录，返回重算条数。"""
        rows = store.rows(MODULE)
        for row in rows:
            row["危害等级"] = self.classify(row.get("发生面积"))
        return len(rows)

    def update_grade_rules(self, severe: float, moderate: float) -> tuple[dict[str, float] | None, str]:
        """调整等级判定标准并立即重算已有记录；标准不合法时原样拒绝，不动任何数据。"""
        if severe <= moderate:
            return None, f"重度阈值（{severe:g}）必须大于中度阈值（{moderate:g}），等级标准未更新"
        if moderate <= 0:
            return None, f"中度阈值（{moderate:g}）必须为正数，等级标准未更新"
        self.severe_threshold = severe
        self.moderate_threshold = moderate
        self.regrade_all()
        return self.grade_rules(), "危害等级判定标准已更新，全部防治记录已按新标准重算"

    # ---- 筛选与排序（清单 / 导出 / 缺药剂清单共用同一份口径） ------------

    @staticmethod
    def _has_chemical(row: dict[str, Any]) -> bool:
        return bool(_to_text(row.get("防治药剂")))

    def _query_rows(
        self,
        *,
        keyword: str | None = None,
        plant: str | None = None,
        species: str | None = None,
        status: str | None = None,
        missing_chemical: bool = False,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        keyword = (keyword or "").strip()
        plant = (plant or "").strip()
        species = (species or "").strip()
        status = (status or "").strip()
        if keyword:
            rows = [row for row in rows if keyword in _to_text(row.get("防治编号"))]
        if plant:
            # 受害植物用包含匹配，输入简称、别名片段也要能查全
            rows = [row for row in rows if plant in _to_text(row.get("受害植物"))]
        if species:
            rows = [row for row in rows if species in _to_text(row.get("病虫种类"))]
        if status:
            rows = [row for row in rows if _to_text(row.get("status")) == status]
        if missing_chemical:
            rows = [row for row in rows if not self._has_chemical(row)]
        return self._sort_rows(rows)

    @staticmethod
    def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """危害等级高的排前面（重度 > 中度 > 轻度），同等级按防治编号、id 兜底，保证顺序确定。"""
        grade_rank = {grade: index for index, grade in enumerate(GRADE_ORDER)}

        def sort_key(row: dict[str, Any]) -> tuple[int, str, int]:
            grade = _to_text(row.get("危害等级"))
            return (
                grade_rank.get(grade, len(GRADE_ORDER)),
                _to_text(row.get("防治编号")),
                int(row.get("id", 0) or 0),
            )

        return sorted(rows, key=sort_key)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        plant: str | None = None,
        species: str | None = None,
        status: str | None = None,
        missing_chemical: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._query_rows(
            keyword=keyword,
            plant=plant,
            species=species,
            status=status,
            missing_chemical=missing_chemical,
        )
        total = len(rows)
        page = max(page, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def missing_chemical_entries(
        self,
        *,
        plant: str | None = None,
        species: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """单独列出没填防治药剂的记录，排序与主清单完全一致。"""
        rows = self._query_rows(plant=plant, species=species, missing_chemical=True)
        return rows, len(rows)

    def count_entries(self, **filters: Any) -> int:
        """与清单同一份筛选口径的条数，供其他页面/看板取数，保证各处条数对得上。"""
        return len(self._query_rows(**filters))

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _to_text(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in [*REQUIRED_FIELDS, *OPTIONAL_FIELDS]:
            value = values.get(field)
            entry[field] = None if (value is None or not _to_text(value)) else value
        entry["危害等级"] = self.classify(entry.get("发生面积"))
        entry["status"] = STATUS_ORDER[0]
        entry["防治状态"] = STATUS_ORDER[0]
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
        entry["防治状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"防治记录已{action}"
