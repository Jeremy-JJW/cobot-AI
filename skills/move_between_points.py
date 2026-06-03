from skills.base import get_point_pose


def run(session, params: dict, context: dict) -> None:
    named_points = context["named_points"]
    from_pose = get_point_pose(params["from_point"], named_points)
    to_pose = get_point_pose(params["to_point"], named_points)
    speed = int(params.get("speed_percent", 30))
    move_type = params.get("move_type", "movj")
    move_fn = session.movl if move_type == "movl" else session.movj

    move_fn(from_pose, v=speed)
    # 中間途經點（先去A再去B再去C...）
    for via in params.get("via_points", []):
        via_pose = get_point_pose(via, named_points)
        move_fn(via_pose, v=speed)
    move_fn(to_pose, v=speed)
