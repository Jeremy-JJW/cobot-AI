from skills.base import get_point_pose


def run(session, params: dict, context: dict) -> None:
    named_points = context["named_points"]
    pose = get_point_pose(params["point"], named_points)
    speed = int(params.get("speed_percent", 30))
    move_type = params.get("move_type", "movj")

    if move_type == "movl":
        session.movl(pose, v=speed)
    else:
        session.movj(pose, v=speed)
