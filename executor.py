"""Skill 白名单执行器：只运行 skill_registry.json 中注册的动作。"""
import json
from typing import Any

from robot_session import RobotSession
from skills import SKILL_HANDLERS, check_workspace_boundary, load_named_points, load_registry, validate_skill_plan


def execute_skill(
    session: RobotSession | None,
    plan: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    registry = load_registry()
    validated = validate_skill_plan(plan, registry)
    skill_name = validated["skill"]
    params = validated["params"]
    explain = validated["explain"]

    print(f"Skill: {skill_name}")
    print(f"说明: {explain}")
    print(f"参数: {json.dumps(params, ensure_ascii=False)}")

    if dry_run or session is None:
        return validated

    context = {
        "named_points": load_named_points(),
        "registry": registry,
    }

    # Workspace boundary check: reject targets outside the safety zone
    check_workspace_boundary(
        skill_name,
        params,
        session.get_pose(),
        context["named_points"],
        current_joints=session.get_joints(),
    )

    handler = SKILL_HANDLERS.get(skill_name)
    if handler is None:
        raise ValueError(f"Skill 未实现: {skill_name}")

    skill_result = handler(session, params, context)
    if skill_result:
        validated = {**validated, "result": skill_result}
    return validated
