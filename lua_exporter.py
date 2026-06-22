"""将脚本程序 IR 转换为越疆 Lua5 脚本文本。映射依据 lua_commands.md。"""
from typing import Any


def _fmt_num(value: float) -> str:
    f = float(value)
    return str(int(f)) if f.is_integer() else f"{f:.3f}".rstrip("0").rstrip(".")


def _fmt_pose(pose: list[float]) -> str:
    return "{pose={" + ", ".join(_fmt_num(v) for v in pose) + "}}"


def _state_const(state) -> str:
    return "ON" if str(state).strip().upper() == "ON" else "OFF"


def _emit_skill(inst: dict[str, Any]) -> list[str]:
    """单条指令（不含条件）对应的 Lua 语句行。"""
    skill = inst["skill"]
    params = inst.get("params", {})

    if skill == "set_speed":
        return [f"SpeedFactor({int(params['speed_percent'])})"]

    if skill == "move_to_program_point":
        point = params["point"]
        speed = int(params.get("speed_percent", 30))
        if params.get("move_type") == "movl":
            return [f"MovL({point}, {{v={speed}, cp=50}})"]
        return [f"MovJ({point}, {{v={speed}}})"]

    if skill == "set_do":
        return [f"DO({int(params['index'])}, {_state_const(params['state'])})"]

    if skill == "wait_di":
        timeout_ms = int(float(params.get("timeout_seconds", 10)) * 1000)
        return [f'Wait("DI({int(params["index"])}) == {_state_const(params["state"])}", {timeout_ms})']

    if skill == "wait":
        return [f"Wait({int(float(params['seconds']) * 1000)})"]

    if skill == "move_relative_linear":
        axis = params["axis"]
        dist = float(params["distance_mm"])
        if params.get("direction") == "-":
            dist = -dist
        offset = {"x": [dist, 0, 0, 0, 0, 0], "y": [0, dist, 0, 0, 0, 0], "z": [0, 0, dist, 0, 0, 0]}[axis]
        return [f"RelMovL({{{', '.join(_fmt_num(v) for v in offset)}}})"]

    return [f"-- 暂不支持导出的指令: {skill}"]


def _emit_instruction(inst: dict[str, Any]) -> list[str]:
    body = _emit_skill(inst)
    condition = inst.get("condition")
    if not condition:
        return body
    di = int(condition["di"])
    state = _state_const(condition.get("state", "ON"))
    lines = [f"if DI({di}) == {state} then"]
    lines.extend("  " + line for line in body)
    lines.append("end")
    return lines


def export_lua(program: dict[str, Any]) -> str:
    lines: list[str] = [
        "-- 由 COBOT AI 脚本编程模式自动生成",
        f"-- 程序名称: {program.get('name', '')}",
        "",
    ]

    points = program.get("points", [])
    if points:
        lines.append("-- 点位定义")
        for p in points:
            lines.append(f"{p['id']} = {_fmt_pose(p['pose'])}")
        lines.append("")

    lines.append("-- 程序主体")
    for inst in program.get("instructions", []):
        text = inst.get("text")
        if text:
            lines.append(f"-- {text}")
        lines.extend(_emit_instruction(inst))

    return "\n".join(lines) + "\n"
