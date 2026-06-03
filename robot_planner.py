"""Self-owned natural language planner for robot Skill JSON."""
import re
from typing import Any

from rule_parser import parse_text
from semantic_cache import lookup_plan


def _convert_legacy_step_plan(llm_plan: dict[str, Any], text: str) -> dict[str, Any]:
    """Convert older LLM steps output into the current single-skill plan."""
    step = llm_plan.get("steps", [{}])[0]
    action = step.get("action", "")
    mapping = {
        "movl_relative": "move_relative_linear",
        "movj_relative": "move_relative_linear",
        "movj": "move_to_named_point",
        "movl": "move_to_named_point",
        "speed": "set_speed",
        "sleep": "wait",
    }
    skill = mapping.get(action)
    if not skill:
        raise ValueError(f"大模型返回了未支持的動作: {action}")

    params: dict[str, Any] = {}
    if skill == "move_relative_linear":
        for axis, key in zip("xyz", ("dx", "dy", "dz")):
            if key in step:
                params["axis"] = axis
                params["direction"] = "+" if float(step[key]) >= 0 else "-"
                params["distance_mm"] = abs(float(step[key]))
                break
    elif skill == "move_to_named_point" and "point" in step:
        params["point"] = step["point"]
    elif skill == "set_speed":
        params["speed_percent"] = step.get("percent", 30)
    elif skill == "wait":
        params["seconds"] = step.get("seconds", 1)

    return {
        "skill": skill,
        "params": params,
        "explain": llm_plan.get("explain", text),
        "source": "llm",
    }


def _looks_complex_for_rule(text: str) -> bool:
    """Return True for instructions where rule parsing should not take shortcuts."""
    compact = re.sub(r"\s+", "", text)
    sequence_markers = ("先", "再", "然後", "接着", "隨後", "第一步", "第二步", "第三步", "，", ",", "；", ";")
    has_sequence = any(marker in compact for marker in sequence_markers)
    speed_mentions = len(re.findall(r"[\d.]+\s*(?:%|％)|慢點|慢一點|快速|快點|快一點|低速", text))

    # 多点序列：涉及 2+ 個命名點的順序訪問 → 走 LLM 更精準
    has_multi_point = False
    if has_sequence:
        points = re.findall(
            r"(?:先|再|然後|接着|之後)?\s*(?:去|到|回|回到|移動(?:到)?)\s*([a-zA-Z0-9_]+)",
            text,
            re.I,
        )
        named = [p for p in points if re.search(r"[a-zA-Z]", p)]
        has_multi_point = len(set(p.lower() for p in named)) >= 2

    return (
        has_multi_point
        or (has_sequence and len(compact) >= 20)
        or (has_sequence and speed_mentions >= 1)
        or speed_mentions >= 2
    )


def _plan_with_llm(text: str) -> dict[str, Any]:
    from llm_planner import plan_from_text as plan_with_llm

    llm_plan = plan_with_llm(text)
    if "skill" in llm_plan:
        llm_plan["source"] = "llm"
        return llm_plan

    return _convert_legacy_step_plan(llm_plan, text)


def plan_from_text(text: str, use_llm: bool = False) -> dict[str, Any]:
    """Plan a user command with rules first and optional LLM fallback."""
    cached_plan = lookup_plan(text)
    if cached_plan is not None:
        return cached_plan

    if use_llm and _looks_complex_for_rule(text):
        return _plan_with_llm(text)

    plan = parse_text(text)
    if plan is not None:
        plan["source"] = "rule"
        return plan

    if not use_llm:
        raise ValueError(
            "無法識別指令。請使用固定話術，見 使用說明.md；"
            "或去掉 --no-llm 使用大模型兜底。"
        )

    return _plan_with_llm(text)
