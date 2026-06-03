"""Human-readable plan summaries for the Web UI."""
from typing import Any

SOURCE_LABELS = {
    "cache": "經驗庫命中",
    "rule": "規則解析",
    "llm": "模型解析",
}

PATTERN_LABELS = {
    "circle_xy": ("繪製圓形軌跡", "XY"),
    "circle_xz": ("繪製圓形軌跡", "XZ"),
    "circle_yz": ("繪製圓形軌跡", "YZ"),
    "arc_xy": ("走圓弧軌跡", "XY"),
    "arc_xz": ("走圓弧軌跡", "XZ"),
    "arc_yz": ("走圓弧軌跡", "YZ"),
    "square_xy": ("走方形路線", "XY"),
    "rectangle_xy": ("走矩形路線", "XY"),
    "triangle_xy": ("走三角形路線", "XY"),
    "diamond_xy": ("走菱形路線", "XY"),
    "cross_xy": ("走十字形路線", "XY"),
    "zigzag_x": ("走鋸齒路線", "X"),
    "wave_y": ("走波浪路線", "Y"),
    "u_shape_xy": ("走 U 型軌跡", "XY"),
    "l_shape_xyz": ("走 L 型軌跡", "XYZ"),
    "box_outline": ("走箱體輪廓", "XYZ"),
    "spiral_z": ("走三維螺旋", "XYZ"),
    "xyz_step_return": ("三軸步進並返回", "XYZ"),
    "xz_lift_return": ("XZ 抬升返回", "XZ"),
    "yz_lift_return": ("YZ 抬升返回", "YZ"),
}

AXIS_NAMES = {"x": "X", "y": "Y", "z": "Z"}
POINT_LABELS = {
    "home": "home（原點）",
    "point_a": "A 點",
    "point_b": "B 點",
}


def source_label(source: str | None) -> str:
    return SOURCE_LABELS.get(source or "", "未知來源")


def source_status_message(source: str | None) -> str:
    if source == "cache":
        return "已從經驗庫找到相似動作"
    if source == "rule":
        return "已用規則識別動作"
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
        direction_text = "正" if direction == "+" else "負"
        headline = f"向 {axis} {direction_text}方向移動 {params.get('distance_mm')} 毫米"
    elif skill == "move_relative_sequence":
        steps = params.get("steps") or []
        parts = [
            f"{AXIS_NAMES.get(str(s.get('axis', '')).lower(), '?')}"
            f"{'+' if s.get('direction') == '+' else '-'}"
            f"{s.get('distance_mm')}mm"
            for s in steps
        ]
        headline = f"按順序移動：{' → '.join(parts)}"
    elif skill == "move_to_named_point":
        point = POINT_LABELS.get(str(params.get("point", "")), params.get("point", ""))
        headline = f"移動到 {point}"
    elif skill == "move_between_points":
        from_point = POINT_LABELS.get(str(params.get("from_point", "")), params.get("from_point", ""))
        to_point = POINT_LABELS.get(str(params.get("to_point", "")), params.get("to_point", ""))
        headline = f"從 {from_point} 移動到 {to_point}"
    elif skill == "motion_pattern":
        pattern = str(params.get("pattern", ""))
        label, plane = PATTERN_LABELS.get(pattern, ("執行復合軌跡", ""))
        if "radius_mm" in params:
            headline = f"{label}，半徑 {params['radius_mm']} 毫米"
        elif "size_mm" in params:
            headline = f"{label}，尺寸 {params['size_mm']} 毫米"
        else:
            headline = label
        if plane:
            headline += f"（{plane} 平面）"
    elif skill == "set_speed":
        headline = f"設置速度爲 {params.get('speed_percent')}%"
    elif skill == "wait":
        headline = f"等待 {params.get('seconds')} 秒"
    elif skill == "read_pose":
        save_as = params.get("save_as")
        headline = f"記錄當前位姿爲 {save_as}" if save_as else "讀取當前位姿"
    elif skill == "stop_or_disable":
        headline = "關閉機械臂使能" if params.get("action") == "disable" else "停止機械臂"
    elif skill == "move_joint":
        joint = params.get("joint", "")
        angle = params.get("angle_deg", "")
        direction = params.get("direction", "+")
        direction_text = "正" if direction == "+" else "負"
        headline = f"關節 {joint} {direction_text}方向旋轉 {angle} 度"
    elif skill == "enable_robot":
        headline = "上使能機械臂"
    else:
        headline = skill or "未知動作"

    lines = [f"動作：{headline}"]
    speed = params.get("speed_percent")
    if speed is not None and skill not in {"set_speed"}:
        lines.append(f"速度：{speed}%")
    move_type = params.get("move_type")
    if move_type:
        lines.append(f"方式：{'關節運動' if move_type == 'movj' else '直線運動'}")
    return "\n".join(lines)


def format_understood_message(plan: dict[str, Any]) -> str:
    parts = []
    for line in format_plan_summary(plan).splitlines():
        if "：" in line:
            parts.append(line.split("：", 1)[1])
        else:
            parts.append(line)
    return f"已明白你想要的動作：{'，'.join(parts)}"


def format_confirm_message(plan: dict[str, Any]) -> str:
    summary = format_plan_summary(plan).replace("\n", "；")
    return f"已明白你想要的動作：{summary}。請確認是否執行。"


def format_pose_text(pose: list[float]) -> str:
    labels = ("X", "Y", "Z", "RX", "RY", "RZ")
    parts = [f"{labels[i]}={pose[i]:.2f}" for i in range(min(len(labels), len(pose)))]
    return "，".join(parts)


def format_executing_message(plan: dict[str, Any]) -> str:
    skill = plan.get("skill")
    if skill == "read_pose":
        return "正在讀取當前位姿"
    return "正在控制機器人運動"


def format_completion_message(plan: dict[str, Any]) -> str:
    skill = plan.get("skill")
    result = plan.get("result") or {}
    if skill == "read_pose":
        pose = result.get("pose")
        if not pose:
            return "未能讀取位姿，請檢查機械臂連接"
        pose_text = format_pose_text(pose)
        save_as = (plan.get("params") or {}).get("save_as") or result.get("save_as")
        if save_as:
            return f"已記錄爲 {save_as}，當前位姿：{pose_text}"
        return f"當前位姿：{pose_text}"
    return "動作已完成"
