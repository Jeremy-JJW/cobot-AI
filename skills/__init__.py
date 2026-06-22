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
from skills.move_to_program_point import run as move_to_program_point
from skills.read_pose import run as read_pose
from skills.set_do import run as set_do
from skills.set_speed import run as set_speed
from skills.enable_robot import run as enable_robot
from skills.joint_move import run as joint_move
from skills.stop_or_disable import run as stop_or_disable
from skills.wait import run as wait
from skills.wait_di import run as wait_di

SKILL_HANDLERS = {
    "move_relative_linear": move_relative_linear,
    "move_relative_sequence": move_relative_sequence,
    "move_to_named_point": move_to_named_point,
    "move_between_points": move_between_points,
    "move_to_program_point": move_to_program_point,
    "motion_pattern": motion_pattern,
    "set_speed": set_speed,
    "set_do": set_do,
    "wait": wait,
    "wait_di": wait_di,
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
