from skills.base import get_point_pose


def run(session, params: dict, context: dict) -> None:
    axis_map = {"x": 0, "y": 1, "z": 2}
    axis = params["axis"]
    direction = params["direction"]
    distance = float(params["distance_mm"])
    speed = int(params.get("speed_percent", 30))

    current = session.get_pose()
    offset = distance if direction == "+" else -distance
    current[axis_map[axis]] += offset
    session.movl(current, v=speed)
