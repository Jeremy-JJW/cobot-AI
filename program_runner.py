"""脚本程序在线逐行执行器：复用白名单 Skill，逐条执行整段程序。"""
from typing import Any

from skills import SKILL_HANDLERS, load_named_points, load_registry, validate_skill_plan


def _program_points(program: dict[str, Any]) -> dict[str, list[float]]:
    return {p["id"]: list(p["pose"]) for p in program.get("points", [])}


def _condition_met(session, condition: dict | None) -> bool:
    if not condition:
        return True
    index = int(condition["di"])
    want = 1 if str(condition.get("state", "ON")).strip().upper() == "ON" else 0
    return session.read_di(index) == want


def run_program(program: dict[str, Any], session) -> dict[str, Any]:
    """逐行执行程序，返回执行统计。session 需已连接并使能。"""
    instructions = program.get("instructions", [])
    context = {
        "program_points": _program_points(program),
        "named_points": load_named_points(),
        "registry": load_registry(),
    }

    executed = 0
    skipped = 0
    for idx, inst in enumerate(instructions, start=1):
        if not _condition_met(session, inst.get("condition")):
            skipped += 1
            continue

        plan = {"skill": inst["skill"], "params": inst.get("params", {})}
        validated = validate_skill_plan(plan, context["registry"])
        handler = SKILL_HANDLERS.get(validated["skill"])
        if handler is None:
            raise ValueError(f"第 {idx} 行 Skill 未實現: {validated['skill']}")
        handler(session, validated["params"], context)
        executed += 1

    return {"executed": executed, "skipped": skipped, "total": len(instructions)}
