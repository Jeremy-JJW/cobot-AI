from skills.base import (
    check_workspace_boundary,
    load_named_points,
    load_registry,
    resolve_point_name,
    validate_skill_plan,
)
from skills.move_between_points import run as move_between_points
from skills.motion_pattern import run as motion_pattern
from skills.move_relative_linear import run as move_relative_linear
from skills.move_relative_sequence import run as move_relative_sequence
from skills.move_to_named_point import run as move_to_named_point
from skills.read_pose import run as read_pose
from skills.set_speed import run as set_speed
from skills.enable_robot import run as enable_robot
from skills.joint_move import run as joint_move
from skills.stop_or_disable import run as stop_or_disable
from skills.wait import run as wait

SKILL_HANDLERS = {
    "move_relative_linear": move_relative_linear,
    "move_relative_sequence": move_relative_sequence,
    "move_to_named_point": move_to_named_point,
    "move_between_points": move_between_points,
    "motion_pattern": motion_pattern,
    "set_speed": set_speed,
    "wait": wait,
    "read_pose": read_pose,
    "stop_or_disable": stop_or_disable,
    "enable_robot": enable_robot,
    "move_joint": joint_move,
}

__all__ = [
    "SKILL_HANDLERS",
    "check_workspace_boundary",
    "load_named_points",
    "load_registry",
    "resolve_point_name",
    "validate_skill_plan",
]
