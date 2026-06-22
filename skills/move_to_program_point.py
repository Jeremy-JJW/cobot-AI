def run(session, params: dict, context: dict) -> None:
    program_points = context.get("program_points", {})
    point_id = params["point"]
    if point_id not in program_points:
        raise ValueError(f"未知程序存點: {point_id}，請先在存點列表中添加")
    pose = list(program_points[point_id])
    speed = int(params.get("speed_percent", 30))
    if params.get("move_type") == "movl":
        session.movl(pose, v=speed)
    else:
        session.movj(pose, v=speed)
