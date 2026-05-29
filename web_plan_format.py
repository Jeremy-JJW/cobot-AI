"""Human-readable plan summaries for the Web UI."""
from typing import Any

SOURCE_LABELS = {
    "cache": "经验库命中",
    "rule": "规则解析",
    "llm": "模型解析",
}

PATTERN_LABELS = {
    "circle_xy": ("绘制圆形轨迹", "XY"),
    "circle_xz": ("绘制圆形轨迹", "XZ"),
    "circle_yz": ("绘制圆形轨迹", "YZ"),
    "arc_xy": ("走圆弧轨迹", "XY"),
    "arc_xz": ("走圆弧轨迹", "XZ"),
    "arc_yz": ("走圆弧轨迹", "YZ"),
    "square_xy": ("走方形路线", "XY"),
    "rectangle_xy": ("走矩形路线", "XY"),
    "triangle_xy": ("走三角形路线", "XY"),
    "diamond_xy": ("走菱形路线", "XY"),
    "cross_xy": ("走十字形路线", "XY"),
    "zigzag_x": ("走锯齿路线", "X"),
    "wave_y": ("走波浪路线", "Y"),
    "u_shape_xy": ("走 U 型轨迹", "XY"),
    "l_shape_xyz": ("走 L 型轨迹", "XYZ"),
    "box_outline": ("走箱体轮廓", "XYZ"),
    "spiral_z": ("走三维螺旋", "XYZ"),
    "xyz_step_return": ("三轴步进并返回", "XYZ"),
    "xz_lift_return": ("XZ 抬升返回", "XZ"),
    "yz_lift_return": ("YZ 抬升返回", "YZ"),
}

AXIS_NAMES = {"x": "X", "y": "Y", "z": "Z"}
POINT_LABELS = {
    "home": "home（原点）",
    "point_a": "A 点",
    "point_b": "B 点",
}


def source_label(source: str | None) -> str:
    return SOURCE_LABELS.get(source or "", "未知来源")


def source_status_message(source: str | None) -> str:
    if source == "cache":
        return "已从经验库找到相似动作"
    if source == "rule":
        return "已用规则识别动作"
    if source == "llm":
        return "模型分析中"
    return "正在理解你的指令..."


def format_plan_summary(plan: dict[str, Any]) -> str:
    skill = plan.get("skill", "")
    params = plan.get("params") or {}
    explain = plan.get("explain", "")

    if explain:
        headline = explain
    elif skill == "move_relative_linear":
        axis = AXIS_NAMES.get(str(params.get("axis", "")).lower(), "?")
        direction = "+" if params.get("direction") == "+" else "-"
        direction_text = "正" if direction == "+" else "负"
        headline = f"向 {axis} {direction_text}方向移动 {params.get('distance_mm')} 毫米"
    elif skill == "move_relative_sequence":
        steps = params.get("steps") or []
        parts = [
            f"{AXIS_NAMES.get(str(s.get('axis', '')).lower(), '?')}"
            f"{'+' if s.get('direction') == '+' else '-'}"
            f"{s.get('distance_mm')}mm"
            for s in steps
        ]
        headline = f"按顺序移动：{' → '.join(parts)}"
    elif skill == "move_to_named_point":
        point = POINT_LABELS.get(str(params.get("point", "")), params.get("point", ""))
        headline = f"移动到 {point}"
    elif skill == "move_between_points":
        from_point = POINT_LABELS.get(str(params.get("from_point", "")), params.get("from_point", ""))
        to_point = POINT_LABELS.get(str(params.get("to_point", "")), params.get("to_point", ""))
        headline = f"从 {from_point} 移动到 {to_point}"
    elif skill == "motion_pattern":
        pattern = str(params.get("pattern", ""))
        label, plane = PATTERN_LABELS.get(pattern, ("执行复合轨迹", ""))
        if "radius_mm" in params:
            headline = f"{label}，半径 {params['radius_mm']} 毫米"
        elif "size_mm" in params:
            headline = f"{label}，尺寸 {params['size_mm']} 毫米"
        else:
            headline = label
        if plane:
            headline += f"（{plane} 平面）"
    elif skill == "set_speed":
        headline = f"设置速度为 {params.get('speed_percent')}%"
    elif skill == "wait":
        headline = f"等待 {params.get('seconds')} 秒"
    elif skill == "read_pose":
        save_as = params.get("save_as")
        headline = f"记录当前位姿为 {save_as}" if save_as else "读取当前位姿"
    elif skill == "stop_or_disable":
        headline = "关闭机械臂使能" if params.get("action") == "disable" else "停止机械臂"
    elif skill == "enable_robot":
        headline = "上使能机械臂"
    else:
        headline = skill or "未知动作"

    lines = [f"动作：{headline}"]
    speed = params.get("speed_percent")
    if speed is not None and skill not in {"set_speed"}:
        lines.append(f"速度：{speed}%")
    move_type = params.get("move_type")
    if move_type:
        lines.append(f"方式：{'关节运动' if move_type == 'movj' else '直线运动'}")
    return "\n".join(lines)


def format_understood_message(plan: dict[str, Any]) -> str:
    parts = []
    for line in format_plan_summary(plan).splitlines():
        if "：" in line:
            parts.append(line.split("：", 1)[1])
        else:
            parts.append(line)
    return f"已明白你想要的动作：{'，'.join(parts)}"


def format_confirm_message(plan: dict[str, Any]) -> str:
    summary = format_plan_summary(plan).replace("\n", "；")
    return f"已明白你想要的动作：{summary}。请确认是否执行。"


def format_pose_text(pose: list[float]) -> str:
    labels = ("X", "Y", "Z", "RX", "RY", "RZ")
    parts = [f"{labels[i]}={pose[i]:.2f}" for i in range(min(len(labels), len(pose)))]
    return "，".join(parts)


def format_executing_message(plan: dict[str, Any]) -> str:
    skill = plan.get("skill")
    if skill == "read_pose":
        return "正在读取当前位姿"
    return "正在控制机器人运动"


def format_completion_message(plan: dict[str, Any]) -> str:
    skill = plan.get("skill")
    result = plan.get("result") or {}
    if skill == "read_pose":
        pose = result.get("pose")
        if not pose:
            return "未能读取位姿，请检查机械臂连接"
        pose_text = format_pose_text(pose)
        save_as = (plan.get("params") or {}).get("save_as") or result.get("save_as")
        if save_as:
            return f"已记录为 {save_as}，当前位姿：{pose_text}"
        return f"当前位姿：{pose_text}"
    return "动作已完成"
