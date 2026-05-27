def run(session, params: dict, context: dict) -> None:
    axis_map = {"x": 0, "y": 1, "z": 2}
    speed = int(params.get("speed_percent", 30))

    for step in params["steps"]:
        axis = step["axis"]
        direction = step["direction"]
        distance = float(step["distance_mm"])
        current = session.get_pose()
        offset = distance if direction == "+" else -distance
        current[axis_map[axis]] += offset
        session.movl(current, v=speed)
