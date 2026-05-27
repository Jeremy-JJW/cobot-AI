from skills.base import get_point_pose


def run(session, params: dict, context: dict) -> None:
    named_points = context["named_points"]
    from_pose = get_point_pose(params["from_point"], named_points)
    to_pose = get_point_pose(params["to_point"], named_points)
    speed = int(params.get("speed_percent", 30))
    move_type = params.get("move_type", "movj")
    move_fn = session.movl if move_type == "movl" else session.movj

    move_fn(from_pose, v=speed)
    move_fn(to_pose, v=speed)
