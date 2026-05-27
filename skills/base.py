import json
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "skill_registry.json"
POSITIONS_PATH = Path(__file__).resolve().parent.parent / "positions.json"

POINT_ALIASES = {
    "a": "point_a",
    "a点": "point_a",
    "b": "point_b",
    "b点": "point_b",
    "home": "home",
    "原点": "home",
    "零点": "home",
}


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_named_points() -> dict[str, list[float]]:
    if not POSITIONS_PATH.exists():
        return {}
    data = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    return data.get("points", data)


def resolve_point_name(name: str) -> str:
    key = name.strip().lower()
    if key in POINT_ALIASES:
        return POINT_ALIASES[key]
    return name.strip()


def get_point_pose(name: str, named_points: dict[str, list[float]]) -> list[float]:
    resolved = resolve_point_name(name)
    if resolved not in named_points:
        raise ValueError(f"未知点位: {name}，可用: {', '.join(named_points.keys())}")
    return list(named_points[resolved])


def _coerce_param(value: Any, schema: dict[str, Any]) -> Any:
    if schema.get("type") == "number":
        return float(value)
    if schema.get("type") == "string":
        return str(value).strip()
    return value


def validate_skill_plan(plan: dict[str, Any], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    skill_name = plan.get("skill")
    skills = registry.get("skills", {})
    if skill_name not in skills:
        raise ValueError(f"未注册的 Skill: {skill_name}")

    schema = skills[skill_name]["params"]
    raw_params = plan.get("params") or {}
    limits = registry.get("global_limits", {})
    validated: dict[str, Any] = {}

    for key, rule in schema.items():
        if key in raw_params:
            value = _coerce_param(raw_params[key], rule)
        elif "default" in rule:
            value = rule["default"]
        elif rule.get("required"):
            raise ValueError(f"Skill {skill_name} 缺少参数: {key}")
        else:
            continue

        if rule.get("type") == "string" and "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"参数 {key} 只能是 {rule['enum']}")
        if rule.get("type") == "array":
            validated[key] = raw_params.get(key, value)
            continue
        if rule.get("type") == "number":
            if "min" in rule and value < rule["min"]:
                raise ValueError(f"参数 {key} 不能小于 {rule['min']}")
            if "max" in rule and value > rule["max"]:
                raise ValueError(f"参数 {key} 不能大于 {rule['max']}")

        validated[key] = value

    if skill_name == "move_relative_linear":
        max_distance = limits.get("max_distance_mm", 200)
        if validated["distance_mm"] > max_distance:
            raise ValueError(f"单次移动不能超过 {max_distance}mm")

    if skill_name == "move_relative_sequence":
        steps = raw_params.get("steps")
        max_steps = limits.get("max_sequence_steps", 10)
        if not isinstance(steps, list) or len(steps) < 2:
            raise ValueError("move_relative_sequence 至少需要 2 步")
        if len(steps) > max_steps:
            raise ValueError(f"move_relative_sequence 最多 {max_steps} 步")
        max_distance = limits.get("max_distance_mm", 200)
        validated_steps: list[dict[str, Any]] = []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"第 {index} 步格式无效")
            axis = str(step.get("axis", "")).lower()
            direction = str(step.get("direction", ""))
            if axis not in {"x", "y", "z"}:
                raise ValueError(f"第 {index} 步 axis 只能是 x/y/z")
            if direction not in {"+", "-"}:
                raise ValueError(f"第 {index} 步 direction 只能是 + 或 -")
            distance = float(step["distance_mm"])
            if distance < 0.1 or distance > max_distance:
                raise ValueError(f"第 {index} 步距离必须在 0.1～{max_distance}mm")
            validated_steps.append(
                {"axis": axis, "direction": direction, "distance_mm": distance}
            )
        validated["steps"] = validated_steps

    if skill_name in {"move_to_named_point", "move_between_points"}:
        named_points = load_named_points()
        if skill_name == "move_to_named_point":
            get_point_pose(validated["point"], named_points)
        else:
            get_point_pose(validated["from_point"], named_points)
            get_point_pose(validated["to_point"], named_points)

    return {
        "skill": skill_name,
        "params": validated,
        "explain": plan.get("explain", skills[skill_name]["description"]),
    }
