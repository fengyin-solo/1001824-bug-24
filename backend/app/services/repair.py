"""修复施工业务规则：状态流转、字段校验与筛选口径都收在这里。

关键约定：
- 状态只能按 待开工 → 施工中 → 待验收 → 已完工 的顺序推进，不允许跳步或回退；
  对已经处于目标状态的动作按幂等处理，保证断网重试不会被当成重复提交拦掉。
- 提交验收携带的完成日期、监理人员会先落到修复单上，再写入唯一的验收记录；
  后到的一份覆盖先前内容，一张修复单始终只保留一条验收记录。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "repair"
REQUIRED_FIELDS = ["修复单号", "关联缺陷", "修复方式"]
STATUS_FIELD = "修复状态"
ACCEPT_FIELDS = ["完成日期", "监理人员"]
ACCEPT_RECORD_KEY = "验收记录"
STATUS_ORDER = ["待开工", "施工中", "待验收", "已完工"]
ACTION_RULES = {"确认开工": "施工中", "提交验收": "待验收", "确认完工": "已完工"}
NEXT_ACTION = {"待开工": "确认开工", "施工中": "提交验收", "待验收": "确认完工"}
NEGATIVE_ACTIONS = []


def _sync_status(entry: dict[str, Any]) -> dict[str, Any]:
    """以内部 status 为唯一事实来源，同步列表与详情共用的中文状态字段。"""
    status = str(entry.get("status") or "")
    if status in STATUS_ORDER:
        entry[STATUS_FIELD] = status
        # 除终态外都算待处理，避免待验收被漏算，保证概览卡片口径一致。
        entry["pending"] = status != STATUS_ORDER[-1]
    return entry


def _is_valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
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
        rows = store.rows(MODULE)
        for row in rows:
            _sync_status(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("修复单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _sync_status(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def stats(self) -> dict[str, int]:
        """按当前状态汇总卡片数据，动作执行完重新拉取即可跟着更新。"""
        rows = store.rows(MODULE)
        counters = {status: 0 for status in STATUS_ORDER}
        finished_month = 0
        today = date.today()
        for row in rows:
            _sync_status(row)
            status = str(row.get("status") or "")
            if status in counters:
                counters[status] += 1
            if status == STATUS_ORDER[-1]:
                finished_on = str(row.get("完成日期") or "")
                if _is_valid_date(finished_on):
                    finished = date.fromisoformat(finished_on)
                    if (finished.year, finished.month) == (today.year, today.month):
                        finished_month += 1
        return {
            "待开工": counters["待开工"],
            "施工中": counters["施工中"],
            "待验收": counters["待验收"],
            "已完工": counters["已完工"],
            "本月完工数": finished_month,
        }

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行状态动作。

        返回值多带一个「是否幂等重试」标记：网络中断后前端原样重试时，
        服务端不会再造数据，而是把已经落库的修复单和验收记录原样返回。
        """
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修复单 {entry_id} 不存在或已归档，请刷新列表确认", False
        _sync_status(entry)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于修复施工可执行范围", False
        current = str(entry.get("status") or "")
        if current not in STATUS_ORDER:
            return None, f"修复单当前状态「{current}」无法识别，请联系管理员核对数据", False

        target = ACTION_RULES[action]
        current_index = STATUS_ORDER.index(current)
        target_index = STATUS_ORDER.index(target)

        # 已经在目标状态：幂等成功。提交验收重传时以本次内容覆盖验收记录，
        # 这样断网重试既不报错也不会堆积出第二条记录。
        if current_index == target_index:
            if action == "提交验收":
                message = self._save_acceptance(entry, values)
                if message:
                    return None, message, False
                return entry, "该修复单已在待验收，本次提交内容已覆盖原验收记录", True
            return entry, f"修复单已是{current}状态，无需重复{action}", True

        # 只能走到相邻的下一个状态，跳步与回退都要明确拦下并说明原因。
        if target_index != current_index + 1:
            expected = NEXT_ACTION.get(current)
            if target_index < current_index:
                return None, f"修复单当前为「{current}」，状态不能回退到「{target}」", False
            if expected:
                return None, f"修复单当前为「{current}」，请先执行「{expected}」，不能直接{action}", False
            return None, f"修复单当前为「{current}」，不能{action}", False

        if action == "提交验收":
            message = self._save_acceptance(entry, values)
            if message:
                return None, message, False

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        _sync_status(entry)
        return entry, f"修复单已{action}", False

    def _save_acceptance(
        self,
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> str:
        """写入提交验收的完成日期与监理人员；返回非空字符串表示校验未通过。"""
        payload: dict[str, str] = {}
        for field in ACCEPT_FIELDS:
            # 重试时允许复用此前已经保存过的值，避免用户重新填写。
            incoming = values.get(field)
            text = str(incoming).strip() if incoming is not None else ""
            if not text:
                text = str(entry.get(field) or "").strip()
            payload[field] = text

        missing = [field for field in ACCEPT_FIELDS if not payload[field]]
        if missing:
            return f"提交验收缺少必填信息：{'、'.join(missing)}，请补充后重试（已填内容不会丢失）"
        if not _is_valid_date(payload["完成日期"]):
            return "完成日期格式不正确，请使用 年-月-日（如 2026-09-30）后重试"

        # 完成日期、监理人员先固化到修复单上，保证列表与详情看到同一份内容。
        for field, text in payload.items():
            entry[field] = text

        # 一张单只留一条验收记录：后到的一份整体覆盖，而不是追加堆积。
        entry[ACCEPT_RECORD_KEY] = {
            "完成日期": payload["完成日期"],
            "监理人员": payload["监理人员"],
            "提交时间": date.today().isoformat(),
        }
        return ""
