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


# ── Workspace boundary checking ──

SAFETY_ZONES_PATH = Path(__file__).resolve().parent.parent / "safety_zones.json"

_DEFAULT_SAFETY_ZONES: dict[str, Any] = {
    "safety_zones": {
        "default": {
            "x": {"min": -600.0, "max": 600.0},
            "y": {"min": -600.0, "max": 600.0},
            "z": {"min": 50.0, "max": 700.0},
        }
    }
}

_MOVEMENT_SKILLS = {
    "move_relative_linear",
    "move_relative_sequence",
    "move_to_named_point",
    "move_between_points",
}

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
_AXIS_NAMES = {0: "X", 1: "Y", 2: "Z"}


def load_safety_zones() -> dict[str, Any]:
    if not SAFETY_ZONES_PATH.exists():
        return _DEFAULT_SAFETY_ZONES["safety_zones"]
    try:
        data = json.loads(SAFETY_ZONES_PATH.read_text(encoding="utf-8"))
        return data.get("safety_zones", data)
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_SAFETY_ZONES["safety_zones"]


def _compute_targets(
    skill_name: str,
    params: dict[str, Any],
    current_pose: list[float],
    named_points: dict[str, list[float]],
) -> list[list[float]]:
    """Compute all [x,y,z] targets that the robot will pass through."""
    targets: list[list[float]] = []

    if skill_name == "move_relative_linear":
        axis = params["axis"]
        offset = float(params["distance_mm"])
        if params["direction"] == "-":
            offset = -offset
        target = list(current_pose[:3])
        target[_AXIS_INDEX[axis]] += offset
        targets.append(target)

    elif skill_name == "move_relative_sequence":
        cursor = list(current_pose[:3])
        for step in params["steps"]:
            offset = float(step["distance_mm"])
            if step["direction"] == "-":
                offset = -offset
            cursor[_AXIS_INDEX[step["axis"]]] += offset
            targets.append(list(cursor))

    elif skill_name == "move_to_named_point":
        pose = get_point_pose(params["point"], named_points)
        targets.append(pose[:3])

    elif skill_name == "move_between_points":
        from_pose = get_point_pose(params["from_point"], named_points)
        to_pose = get_point_pose(params["to_point"], named_points)
        targets.append(from_pose[:3])
        targets.append(to_pose[:3])

    return targets


_JOINT_INDEX = {"J1": 0, "J2": 1, "J3": 2, "J4": 3, "J5": 4, "J6": 5}


def _check_joint_boundary(
    params: dict[str, Any],
    current_joints: list[float] | None,
) -> None:
    """Check joint angle limits for move_joint skill."""
    if current_joints is None:
        return
    zones = load_safety_zones()
    zone = next(iter(zones.values()))
    joint_limits = zone.get("joints", {})
    if not joint_limits:
        return

    joint = params["joint"]
    if joint not in joint_limits:
        return

    idx = _JOINT_INDEX[joint]
    offset = float(params["angle_deg"])
    if params["direction"] == "-":
        offset = -offset
    target_angle = current_joints[idx] + offset

    lo = float(joint_limits[joint]["min"])
    hi = float(joint_limits[joint]["max"])

    if target_angle < lo:
        raise ValueError(
            f"目标关节 {joint} 角度 {target_angle:.1f}° 低于安全下限 {lo:.0f}°，已拦截"
        )
    if target_angle > hi:
        raise ValueError(
            f"目标关节 {joint} 角度 {target_angle:.1f}° 超出安全上限 {hi:.0f}°，已拦截"
        )


def check_workspace_boundary(
    skill_name: str,
    params: dict[str, Any],
    current_pose: list[float],
    named_points: dict[str, list[float]],
    current_joints: list[float] | None = None,
) -> None:
    """Raise ValueError if any target position is outside the safety zone."""
    if skill_name == "move_joint":
        _check_joint_boundary(params, current_joints)
        return

    if skill_name not in _MOVEMENT_SKILLS:
        return

    zones = load_safety_zones()
    zone = next(iter(zones.values()))
    if "x" not in zone or "y" not in zone or "z" not in zone:
        return  # malformed config, skip check

    bounds = {
        "X": (float(zone["x"]["min"]), float(zone["x"]["max"])),
        "Y": (float(zone["y"]["min"]), float(zone["y"]["max"])),
        "Z": (float(zone["z"]["min"]), float(zone["z"]["max"])),
    }

    targets = _compute_targets(skill_name, params, current_pose, named_points)

    max_radius = float(zone.get("max_radius_mm", 0))

    for target in targets:
        x, y, z = target[0], target[1], target[2]

        # Axis-aligned check
        for i, axis_name in _AXIS_NAMES.items():
            value = target[i]
            lo, hi = bounds[axis_name]
            if value < lo:
                raise ValueError(
                    f"目标 {axis_name}={value:.1f}mm 低于安全下限 {lo:.0f}mm，已拦截"
                )
            if value > hi:
                raise ValueError(
                    f"目标 {axis_name}={value:.1f}mm 超出安全上限 {hi:.0f}mm，已拦截"
                )

        # Radial distance check (workspace is spherical, not cubic)
        if max_radius > 0:
            radius = (x ** 2 + y ** 2) ** 0.5
            if radius > max_radius:
                raise ValueError(
                    f"目标水平距离 {radius:.0f}mm 超出工作半径 {max_radius:.0f}mm，已拦截"
                )
