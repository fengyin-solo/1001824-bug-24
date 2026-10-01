"""修复施工业务规则：状态流转、字段校验、验收记录与筛选口径都收在这里。

关键约定：
- status 是内部权威状态，列表与详情都从它同步出展示用的「修复状态」，保证两处一致；
- 状态只能按 待开工 → 施工中 → 待验收 → 已完工 的顺序逐格前进，不能跳步、不能回退；
- 一张修复单只保留一条验收记录（acceptance），网络中断后重试提交时后到的一份覆盖旧值，
  不会堆积出多条；
- 提交验收属于幂等动作：在「待验收」状态重复提交不是错误，而是用最新资料覆盖。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "repair"
REQUIRED_FIELDS = ["修复单号", "关联缺陷", "修复方式"]
# 创建时允许一并带上的选填信息
OPTIONAL_FIELDS = ["承接单位", "开挖范围"]
STATUS_ORDER = ["待开工", "施工中", "待验收", "已完工"]
# 每个动作的上一步状态：只允许从上一格顺序流转
ACTION_PREV_STATUS = {"确认开工": "待开工", "提交验收": "施工中", "确认完工": "待验收"}
ACTION_TARGET_STATUS = {"确认开工": "施工中", "提交验收": "待验收", "确认完工": "已完工"}
# 提交验收时必须随单填写的资料，缺一项都不允许进入待验收
ACCEPT_FIELDS = ["完成日期", "监理人员"]


def _sync_display(entry: dict[str, Any]) -> dict[str, Any]:
    """把内部 status 同步到展示列「修复状态」。

    历史数据可能把两个字段写成了不同的值（列表与详情因此不一致），
    任何读路径都先经过这里，以 status 为准对齐。
    """
    status = entry.get("status")
    if status in STATUS_ORDER:
        entry["修复状态"] = status
    return entry


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


class RepairService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_sync_display(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("修复单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _sync_display(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """概览卡片：按当前真实状态统计，不再写死。"""
        rows = store.rows(MODULE)
        today = datetime.today()
        return {
            "待开工": sum(1 for row in rows if row.get("status") == "待开工"),
            "施工中": sum(1 for row in rows if row.get("status") == "施工中"),
            "本月完工": sum(
                1
                for row in rows
                if row.get("status") == "已完工"
                and str(row.get("完成日期", ""))[:7] == f"{today.year}-{today.month:02d}"
            ),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = values[field]
        entry["status"] = STATUS_ORDER[0]
        entry["修复状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修复单 {entry_id} 不存在或已归档"
        if action not in ACTION_TARGET_STATUS:
            return None, f"动作「{action}」不属于修复施工可执行范围"

        current = entry.get("status")
        expected = ACTION_PREV_STATUS[action]
        target = ACTION_TARGET_STATUS[action]

        # 提交验收幂等：已经在待验收说明上一次请求实际已成功（例如网络中断导致前端没收到响应），
        # 重试时用新资料覆盖同一条验收记录，并明确告知用户单据早已生效。
        if action == "提交验收" and current == "待验收":
            message, ok = self._save_acceptance(entry, values or {})
            if not ok:
                return None, message
            return _sync_display(entry), f"该修复单此前已进入待验收，本次资料已覆盖原验收记录"

        # 状态只能按顺序逐格前进
        if current != expected:
            if current == target:
                return None, f"修复单当前已是「{current}」，请勿重复执行「{action}」"
            if current == "已完工":
                return None, f"修复单已完工，流程结束，不能再执行「{action}」"
            order = STATUS_ORDER
            if order.index(str(current)) > order.index(target):
                return None, (
                    f"修复单当前为「{current}」，已经走过「{target}」环节，"
                    f"状态不能回退（只能按 {' → '.join(STATUS_ORDER)} 顺序流转）"
                )
            return None, (
                f"修复单当前为「{current}」，需先完成「{expected}」前置环节，"
                f"不能直接「{action}」（状态只能按 {' → '.join(STATUS_ORDER)} 顺序流转）"
            )

        if action == "提交验收":
            message, ok = self._save_acceptance(entry, values or {})
            if not ok:
                return None, message

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = False
        return _sync_display(entry), f"修复单已{action}"

    def _save_acceptance(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[str, bool]:
        """落唯一一条验收记录；后到的一份覆盖旧值，绝不追加堆积。"""
        missing = [field for field in ACCEPT_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return f"缺少验收必填资料：{'、'.join(missing)}，请补全后重新提交", False
        finish_date = str(values["完成日期"]).strip()
        if not _is_valid_date(finish_date):
            return "完成日期格式应为 YYYY-MM-DD（例如 2026-09-30），请核对后重新提交", False

        acceptance = entry.get("acceptance")
        if not isinstance(acceptance, dict):
            acceptance = {}
        # 同一张单始终只保留这一条记录，重试/补录直接覆盖；提交时间记录最后一次覆盖
        acceptance.clear()
        acceptance.update(
            {
                "完成日期": finish_date,
                "监理人员": str(values["监理人员"]).strip(),
                "提交时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        entry["acceptance"] = acceptance
        for field in ACCEPT_FIELDS:
            entry[field] = acceptance[field]
        return "", True
