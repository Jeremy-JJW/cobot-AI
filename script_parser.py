"""脚本编程模式：把一句话翻译成一条或多条指令 IR。

返回的每条指令形如：
    {"skill": str, "params": dict, "text": str, "condition": dict|None}

识别失败时回落到一期通用解析器 plan_from_text。
"""
import re
from typing import Any

ON_WORDS = {"on", "开", "開", "打开", "打開", "高", "高电平", "高電平", "1"}
OFF_WORDS = {"off", "关", "關", "关闭", "關閉", "低", "低电平", "低電平", "0"}

_COND_RE = re.compile(
    r"^(?:当|當|如果|若)\s*DI\s*(\d+)\s*(?:信号|信號)?\s*(?:为|為|是|=|==|输入|輸入)?\s*"
    r"(ON|OFF|开|開|打开|打開|关|關|关闭|關閉|高|低)\s*(?:时|時|的时候|的時候)?\s*[，,：:]?\s*",
    re.IGNORECASE,
)
_BETWEEN_RE = re.compile(
    r"(?:从|從)\s*P(\d+)\s*(?:点|點)?\s*(?:运动|運動|移动|移動|移|走)?\s*(?:到|至|->|→)\s*P(\d+)",
    re.IGNORECASE,
)
_MOVE_RE = re.compile(
    r"(?:运动|運動|移动|移動|移|走|去|回|回到|到)\s*(?:到|至)?\s*P(\d+)", re.IGNORECASE
)
_SET_DO_RE = re.compile(
    r"DO\s*(\d+)\s*(?:信号|信號|输出|輸出)?\s*(?:为|為|是|=|==|设为|設為|置为|置為|置|设置为|設置為)?\s*"
    r"(ON|OFF|开|開|打开|打開|关|關|关闭|關閉|高|低)",
    re.IGNORECASE,
)
_WAIT_DI_RE = re.compile(
    r"(?:等待|等到|直到|等)\s*DI\s*(\d+)\s*(?:信号|信號)?\s*(?:为|為|是|=|==)?\s*"
    r"(ON|OFF|开|開|打开|打開|关|關|关闭|關閉|高|低)",
    re.IGNORECASE,
)
_SPEED_RE = re.compile(r"(?:速度|速率)\D*?(\d+)")
_WAIT_SEC_RE = re.compile(r"(?:等待|等|停|延时|延時|暂停|暫停)\s*([\d.]+)\s*(?:秒|s)", re.IGNORECASE)


def _norm_state(word: str) -> str:
    return "ON" if word.strip().lower() in ON_WORDS else "OFF"


def _is_linear(text: str) -> bool:
    return "直线" in text or "直線" in text


def describe(skill: str, params: dict[str, Any], fallback: str = "") -> str:
    if skill == "move_to_program_point":
        mode = "直线运动到" if params.get("move_type") == "movl" else "运动到"
        return f"{mode} {params['point']}"
    if skill == "set_do":
        return f"置 DO{int(params['index'])} 为 {params['state']}"
    if skill == "wait_di":
        return f"等待 DI{int(params['index'])} 为 {params['state']}"
    if skill == "set_speed":
        return f"设置速度为 {int(params['speed_percent'])}%"
    if skill == "wait":
        return f"等待 {params['seconds']} 秒"
    return fallback or skill


def _with_condition_text(text: str, condition: dict | None) -> str:
    if not condition:
        return text
    return f"当 DI{int(condition['di'])} 为 {condition['state']} 时，{text}"


def _parse_action(text: str) -> list[dict[str, Any]]:
    """解析去掉条件前缀后的动作，返回 0..n 条指令（不含 condition/text）。"""
    linear = _is_linear(text)
    move_type = "movl" if linear else "movj"

    m = _SET_DO_RE.search(text)
    if m:
        return [{"skill": "set_do", "params": {"index": int(m.group(1)), "state": _norm_state(m.group(2))}}]

    m = _WAIT_DI_RE.search(text)
    if m:
        return [{"skill": "wait_di", "params": {"index": int(m.group(1)), "state": _norm_state(m.group(2))}}]

    m = _BETWEEN_RE.search(text)
    if m:
        return [
            {"skill": "move_to_program_point", "params": {"point": f"P{m.group(1)}", "move_type": move_type}},
            {"skill": "move_to_program_point", "params": {"point": f"P{m.group(2)}", "move_type": move_type}},
        ]

    m = _MOVE_RE.search(text)
    if m:
        return [{"skill": "move_to_program_point", "params": {"point": f"P{m.group(1)}", "move_type": move_type}}]

    m = _WAIT_SEC_RE.search(text)
    if m:
        return [{"skill": "wait", "params": {"seconds": float(m.group(1))}}]

    m = _SPEED_RE.search(text)
    if m:
        return [{"skill": "set_speed", "params": {"speed_percent": int(m.group(1))}}]

    return []


def parse_instruction(text: str, use_llm: bool = True) -> list[dict[str, Any]]:
    """把一句话解析为指令 IR 列表。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("请输入指令")

    condition: dict | None = None
    cond_match = _COND_RE.match(raw)
    body = raw
    if cond_match:
        condition = {"di": int(cond_match.group(1)), "state": _norm_state(cond_match.group(2))}
        body = raw[cond_match.end():].strip()

    actions = _parse_action(body)
    if actions:
        result = []
        for act in actions:
            text_desc = _with_condition_text(describe(act["skill"], act["params"]), condition)
            result.append({**act, "condition": condition, "text": text_desc})
        return result

    # 回落到一期通用解析器（相对移动、画圆等）
    from robot_planner import plan_from_text

    plan = plan_from_text(body, use_llm=use_llm)
    skill = plan.get("skill")
    params = {k: v for k, v in plan.items() if k not in ("skill", "source", "explain")}
    params = plan.get("params", params)
    text_desc = _with_condition_text(describe(skill, params, fallback=plan.get("explain", body)), condition)
    return [{"skill": skill, "params": params, "condition": condition, "text": text_desc}]
