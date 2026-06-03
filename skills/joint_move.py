"""單個關節旋轉控制：讀當前關節 → 修改指定關節 → 關節模式運動。"""
from typing import Any


def run(session, params: dict, context: dict) -> None:
    joint_map = {"J1": 0, "J2": 1, "J3": 2, "J4": 3, "J5": 4, "J6": 5}
    joint_key = params["joint"]
    direction = params["direction"]
    angle = float(params["angle_deg"])
    speed = int(params.get("speed_percent", 30))

    idx = joint_map[joint_key]
    offset = angle if direction == "+" else -angle

    current = session.get_joints()
    target = list(current)
    target[idx] += offset

    session.movj_joint(target, v=speed)
