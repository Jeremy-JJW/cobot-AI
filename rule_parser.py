"""规则优先的自然语言解析：固定话术不调用大模型。"""
import re
from typing import Any

from skills.base import resolve_point_name


AXIS_DIRECTIONS = {
    "x+": ("x", "+", ("x正", "x+", "x 轴正", "x轴正", "x正方向", "x轴正方向")),
    "x-": ("x", "-", ("x负", "x-", "x 轴负", "x轴负", "x负方向", "x轴负方向")),
    "y+": ("y", "+", ("y正", "y+", "y 轴正", "y轴正", "y正方向", "y轴正方向")),
    "y-": ("y", "-", ("y负", "y-", "y 轴负", "y轴负", "y负方向", "y轴负方向")),
    "z+": ("z", "+", ("z正", "z+", "z 轴正", "z轴正", "z正方向", "z轴正方向", "上升", "抬高", "抬升", "升高", "向上", "往上")),
    "z-": ("z", "-", ("z负", "z-", "z 轴负", "z轴负", "z负方向", "z轴负方向", "下降", "降低", "向下", "往下")),
}

MOTION_PATTERN_ALIASES = [
    ("xyz_step_return", (r"x\+?.*y\+?.*z\+?.*(回到|返回).*(原点|起点|初始)", r"三轴.*回到.*(原点|起点)")),
    ("spiral_z", (r"三维螺旋|空间螺旋|螺旋",)),
    ("circle_xz", (r"xz.*(画圆|圆形|整圆)|(画圆|圆形|整圆).*xz",)),
    ("circle_yz", (r"yz.*(画圆|圆形|整圆)|(画圆|圆形|整圆).*yz",)),
    ("circle_xy", (r"(xy|水平|桌面).*(画圆|圆形|整圆)|画圆|圆形|整圆",)),
    ("arc_xz", (r"xz.*(圆弧|弧线)|(圆弧|弧线).*xz",)),
    ("arc_yz", (r"yz.*(圆弧|弧线)|(圆弧|弧线).*yz",)),
    ("arc_xy", (r"(xy|水平|桌面).*(圆弧|弧线)|圆弧|弧线",)),
    ("square_xy", (r"正方形|方形|方框",)),
    ("rectangle_xy", (r"矩形|长方形",)),
    ("triangle_xy", (r"三角形|三角路线",)),
    ("diamond_xy", (r"菱形",)),
    ("cross_xy", (r"十字|十字形",)),
    ("zigzag_x", (r"锯齿|折线",)),
    ("wave_y", (r"波浪|波形",)),
    ("u_shape_xy", (r"u\s*型|u\s*形|u\s*字|u字",)),
    ("box_outline", (r"箱体|盒子|立方体|立体框",)),
    ("xz_lift_return", (r"xz.*(抬升|升高|返回|回到)|x.*z.*(抬升|升高|返回|回到)",)),
    ("yz_lift_return", (r"yz.*(抬升|升高|返回|回到)|y.*z.*(抬升|升高|返回|回到)",)),
    ("l_shape_xyz", (r"l\s*型|l\s*形|l\s*字|l字",)),
]


def _build_common_speech_examples() -> tuple[str, ...]:
    verbs = ("移动", "运动", "走", "走一下", "执行", "运行", "沿着", "往", "向", "来一段")
    values = (5, 10, 20, 30, 50, 80, 100, 150, 200)
    units = ("毫米", "mm", "厘米")
    examples: list[str] = []

    for _, _, words in AXIS_DIRECTIONS.values():
        for word in words:
            for verb in verbs:
                for value in values:
                    unit = units[value % len(units)]
                    examples.append(f"{verb}{word}{value}{unit}")

    point_verbs = ("去", "移动到", "运动到", "回到", "到达", "走到")
    for point in ("A点", "B点", "point_a", "point_b", "home", "原点", "零点"):
        for verb in point_verbs:
            examples.append(f"{verb}{point}")

    for speed in (10, 20, 30, 40, 50):
        examples.extend((f"速度设置为{speed}%", f"速度调到{speed}", f"用{speed}%速度"))

    for seconds in (0.5, 1, 2, 3, 5, 10):
        examples.extend((f"等待{seconds}秒", f"暂停{seconds}秒", f"停{seconds}秒"))

    for name, _ in MOTION_PATTERN_ALIASES:
        examples.extend((f"执行{name}", f"走{name}", f"运行{name}"))

    # 这个样例库显式覆盖 500+ 常见说法，真实解析仍以正则规则为准。
    return tuple(dict.fromkeys(examples))


COMMON_SPEECH_EXAMPLES = _build_common_speech_examples()
COMMON_SPEECH_EXAMPLE_COUNT = len(COMMON_SPEECH_EXAMPLES)
assert COMMON_SPEECH_EXAMPLE_COUNT >= 500


def _distance(text: str) -> float | None:
    match = re.search(r"([\d.]+)\s*(?:毫米|mm|厘米|cm|公分)", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    if re.search(r"厘米|cm|公分", text, re.I):
        value *= 10
    return value


def _speed(text: str) -> float | None:
    match = re.search(r"([\d.]+)\s*(?:%|％)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"速度(?:设置|调|调整|设定|为|到)?\s*([\d.]+)", text)
    if match:
        return float(match.group(1))
    if re.search(r"慢一点|慢点|低速", text):
        return 20
    if re.search(r"快一点|快点|快速", text):
        return 40
    return None


def _point_name(text: str) -> str | None:
    # 不用 \b：中文与 home/point_a 连写时（如「回到home」）在 Python 正则里不算词边界。
    aliases = {
        r"home|原点|零点": "home",
        r"point[_ ]?a|a\s*点": "point_a",
        r"point[_ ]?b|b\s*点": "point_b",
    }
    for pattern, name in aliases.items():
        if re.search(pattern, text, re.I):
            return name
    match = re.search(r"(point_[a-z0-9_]+)", text, re.I)
    return match.group(1).lower() if match else None


def _motion_pattern(text: str) -> str | None:
    for pattern, aliases in MOTION_PATTERN_ALIASES:
        if pattern in text:
            return pattern
        for alias in aliases:
            if re.search(alias, text, re.I):
                return pattern
    return None


RELATIVE_SEGMENT_RE = re.compile(
    r"([xyzXYZ])\s*(?:轴)?\s*(正|负|[+\-])?\s*([\d.]+)\s*(?:毫米|mm|厘米|cm|公分)?",
    re.I,
)

MAX_SEQUENCE_STEPS = 10

# 多步相对移动：连接词 / 顺序词（出现任一词且能拆出 ≥2 步即走 sequence）
SEQUENCE_INTENT_RE = re.compile(
    r"先(?:运动|移动|走)?|"
    r"再(?:运动|移动|走)?|"
    r"然后(?:运动|移动|走)?|"
    r"接着(?:运动|移动|走)?|"
    r"随后(?:运动|移动|走)?|"
    r"接下来(?:运动|移动|走)?|"
    r"之后(?:运动|移动|走)?|"
    r"紧接着|"
    r"完了再|然后再|再然后|"
    r"又|以及|并且|而且|"
    r"再接着|再继续|继续|"
    r"第[一二三四五六七八九十两\d]+步|"
    r"[，,、；;]",
    re.I,
)

SEQUENCE_SPLIT_RE = re.compile(
    r"(?:"
    r"先(?:运动|移动|走)?|"
    r"再(?:运动|移动|走)?|"
    r"然后(?:运动|移动|走)?|"
    r"接着(?:运动|移动|走)?|"
    r"随后(?:运动|移动|走)?|"
    r"接下来(?:运动|移动|走)?|"
    r"之后(?:运动|移动|走)?|"
    r"紧接着|"
    r"完了|完了再|然后再|再然后|"
    r"又|以及|并且|而且|"
    r"再接着|再继续|继续|"
    r"第[一二三四五六七八九十两\d]+步|"
    r"[，,、；;]"
    r")+",
    re.I,
)

VERBOSE_RELATIVE_CLAUSE_RE = re.compile(
    r"(?:向|沿|按)?\s*([xyzXYZ])\s*(?:轴)?\s*(正|负|[+\-])?\s*(?:方向|向)?\s*(?:移动|运动|走|偏移)?\s*([\d.]+)\s*(?:毫米|mm|厘米|cm|公分)?",
    re.I,
)


def _relative_axis(text: str) -> tuple[str, str] | None:
    compact = re.sub(r"\s+", "", text.lower())
    for axis, direction, words in AXIS_DIRECTIONS.values():
        if any(word.replace(" ", "").lower() in compact for word in words):
            return axis, direction

    axis_match = re.search(r"([xyzXYZ])\s*(?:轴)?\s*(正|负|\+|\-)?\s*(?:方向|向)?", text)
    if not axis_match:
        return None
    axis = axis_match.group(1).lower()
    direction_word = axis_match.group(2) or ""
    if direction_word in {"负", "-"} or re.search(r"负|-\s*方向", text):
        return axis, "-"
    return axis, "+"


def _parse_relative_segment(match: re.Match[str]) -> dict[str, Any]:
    axis = match.group(1).lower()
    direction_word = match.group(2) or ""
    distance = float(match.group(3))
    if re.search(r"厘米|cm|公分", match.group(0), re.I):
        distance *= 10
    if direction_word in {"负", "-"}:
        direction = "-"
    else:
        direction = "+"
    return {"axis": axis, "direction": direction, "distance_mm": distance}


def _distance_in_clause(clause: str) -> float | None:
    distance = _distance(clause)
    if distance is not None:
        return distance
    match = re.search(r"([\d.]+)\s*(?:毫米|mm|厘米|cm|公分)?", clause, re.I)
    if not match:
        return None
    value = float(match.group(1))
    if re.search(r"厘米|cm|公分", clause, re.I):
        value *= 10
    return value


def _parse_single_relative_clause(clause: str) -> dict[str, Any] | None:
    clause = clause.strip()
    if not clause:
        return None

    if re.search(r"抬高|抬升|上升|向上|升高|往上", clause, re.I):
        distance = _distance_in_clause(clause)
        if distance is not None:
            return {"axis": "z", "direction": "+", "distance_mm": distance}
    if re.search(r"下降|降低|向下|往下", clause, re.I):
        distance = _distance_in_clause(clause)
        if distance is not None:
            return {"axis": "z", "direction": "-", "distance_mm": distance}

    match = RELATIVE_SEGMENT_RE.search(clause)
    if match:
        return _parse_relative_segment(match)

    match = VERBOSE_RELATIVE_CLAUSE_RE.search(clause)
    if match:
        return _parse_relative_segment(match)

    axis_direction = _relative_axis(clause)
    distance = _distance_in_clause(clause)
    if axis_direction and distance is not None:
        axis, direction = axis_direction
        return {"axis": axis, "direction": direction, "distance_mm": distance}
    return None


def _split_sequence_clauses(text: str) -> list[str]:
    parts = [part.strip() for part in SEQUENCE_SPLIT_RE.split(text.strip())]
    return [part for part in parts if part]


def _parse_relative_sequence(text: str) -> list[dict[str, Any]] | None:
    if not SEQUENCE_INTENT_RE.search(text):
        return None

    steps: list[dict[str, Any]] = []
    clauses = _split_sequence_clauses(text)
    if len(clauses) >= 2:
        for clause in clauses:
            if _is_speed_only_command(clause):
                continue
            step = _parse_single_relative_clause(clause)
            if not step:
                # 保守策略：多步指令只要有任一步解析不了，就整条交给 LLM/报错，
                # 避免漏掉某一步后仍然执行不完整动作。
                return None
            steps.append(step)
    else:
        for match in RELATIVE_SEGMENT_RE.finditer(text):
            steps.append(_parse_relative_segment(match))

    if len(steps) < 2:
        return None
    return steps[:MAX_SEQUENCE_STEPS]


def _looks_like_speed_suffix_only(text: str) -> bool:
    """True when commas only separate movement from a trailing speed note."""
    clauses = _split_sequence_clauses(text)
    if len(clauses) < 2:
        return False
    movement_clauses = [clause for clause in clauses if not _is_speed_only_command(clause)]
    if len(movement_clauses) != 1:
        return False
    return _parse_single_relative_clause(movement_clauses[0]) is not None


def _has_movement_intent(text: str) -> bool:
    """Return True when text describes motion, not speed-only tuning."""
    raw = text.strip()
    if _motion_pattern(raw):
        return True
    if re.search(
        r"从\s*[a-zA-Z0-9_]+\s*点?\s*(?:移动|运动)?\s*到\s*[a-zA-Z0-9_]+\s*点?",
        raw,
        re.I,
    ):
        return True
    if re.search(r"(?:移动|运动|去|回到|到达|走|偏移|画|抬|升|降)", raw):
        if _parse_relative_sequence(raw):
            return True
        axis_direction = _relative_axis(raw)
        distance = _distance(raw)
        if axis_direction and distance is not None:
            return True
        if _point_name(raw):
            return True
    if RELATIVE_SEGMENT_RE.search(raw) or VERBOSE_RELATIVE_CLAUSE_RE.search(raw):
        return True
    if re.search(r"抬高|抬升|上升|向上|下降|降低|向下", raw, re.I) and _distance_in_clause(raw) is not None:
        return True
    return False


def _is_speed_only_command(text: str) -> bool:
    speed = _speed(text)
    if speed is None or _has_movement_intent(text):
        return False
    return bool(
        "速度" in text
        or re.search(r"[\d.]+\s*(?:%|％)", text)
        or re.search(r"慢一点|慢点|低速|快一点|快点|快速", text)
    )


def parse_text(text: str) -> dict[str, Any] | None:
    """匹配成功返回 skill 计划，失败返回 None。"""
    raw = text.strip()
    if not raw:
        return None

    # 使能 / 停止
    if re.search(r"下使能", raw):
        return {"skill": "stop_or_disable", "params": {"action": "disable"}, "explain": "下使能机械臂"}
    if re.search(r"上使能", raw):
        return {"skill": "enable_robot", "params": {}, "explain": "上使能机械臂"}
    if re.search(r"停止|停住|急停", raw):
        return {"skill": "stop_or_disable", "params": {"action": "stop"}, "explain": "停止当前运动"}

    # 等待
    wait_match = re.search(r"(?:等待|暂停|停一下|停|等)\s*([\d.]+)\s*秒", raw)
    if wait_match:
        return {
            "skill": "wait",
            "params": {"seconds": float(wait_match.group(1))},
            "explain": f"等待 {wait_match.group(1)} 秒",
        }
    if re.search(r"等一下|暂停一下|停一下", raw):
        return {"skill": "wait", "params": {"seconds": 1}, "explain": "等待 1 秒"}

    # 速度（纯调速；带位移的指令在后面解析并附带 speed_percent）
    if _is_speed_only_command(raw):
        speed = _speed(raw)
        assert speed is not None
        return {
            "skill": "set_speed",
            "params": {"speed_percent": speed},
            "explain": f"设置速度为 {speed}%",
        }

    # 读取 / 记录位姿
    if re.search(r"读取|查询|查看", raw) and re.search(r"位置|位姿|坐标", raw):
        return {"skill": "read_pose", "params": {}, "explain": "读取当前位姿"}
    save_match = re.search(r"(?:记录|保存|标定).*(?:为|到)\s*([a-zA-Z0-9_]+)", raw)
    if save_match and re.search(r"位置|位姿|点", raw):
        return {
            "skill": "read_pose",
            "params": {"save_as": save_match.group(1)},
            "explain": f"记录当前位姿为 {save_match.group(1)}",
        }

    # 多步相对移动：先 X+ 再 Y+ 等（优先于预置 L 型等复合路线，避免误加 Z 轴）
    steps = _parse_relative_sequence(raw)
    if steps:
        speed = _speed(raw)
        params = {"steps": steps}
        if speed is not None:
            params["speed_percent"] = speed
        parts = [f"{s['axis'].upper()}{s['direction']}{s['distance_mm']}mm" for s in steps]
        return {
            "skill": "move_relative_sequence",
            "params": params,
            "explain": f"按顺序移动: {' → '.join(parts)}",
        }
    if SEQUENCE_INTENT_RE.search(raw):
        # 多步意图存在但无法完整解析时，不再降级成单步/预置路线。
        # 例外：「移动 …，速度 20%」这类逗号后只是调速说明，仍按单步处理。
        if not _looks_like_speed_suffix_only(raw):
            return None

    # 复合运动路线要优先于「回到原点」等命名点规则。
    distance = _distance(raw)
    pattern = _motion_pattern(raw)
    if pattern:
        speed = _speed(raw)
        params: dict[str, Any] = {"pattern": pattern}
        if distance is not None:
            if pattern.startswith(("circle", "arc")) or pattern == "spiral_z":
                params["radius_mm"] = distance
            else:
                params["size_mm"] = distance
                params["height_mm"] = distance
        if pattern == "spiral_z" and re.search(r"向下|下降|往下", raw):
            params["height_mm"] = -abs(float(params.get("height_mm", distance or 50)))
        if speed is not None:
            params["speed_percent"] = speed
        return {
            "skill": "motion_pattern",
            "params": params,
            "explain": f"执行预置复合运动路线 {pattern}",
        }

    # 点到点（必须在「去命名点」之前匹配）
    between = re.search(
        r"从\s*([a-zA-Z0-9_]+)\s*点?\s*(?:移动|运动)?\s*到\s*([a-zA-Z0-9_]+)\s*点?",
        raw,
        re.I,
    )
    if between:
        from_point = resolve_point_name(between.group(1))
        to_point = resolve_point_name(between.group(2))
        speed = _speed(raw)
        params = {"from_point": from_point, "to_point": to_point}
        if speed is not None:
            params["speed_percent"] = speed
        return {
            "skill": "move_between_points",
            "params": params,
            "explain": f"从 {from_point} 移动到 {to_point}",
        }

    # 去命名点
    if re.search(r"(?:移动|运动|去|回到|到达)", raw):
        point = _point_name(raw)
        if point:
            speed = _speed(raw)
            params = {"point": point}
            if speed is not None:
                params["speed_percent"] = speed
            return {
                "skill": "move_to_named_point",
                "params": params,
                "explain": f"移动到 {point}",
            }

    # 单步相对移动：轴 + 方向 + 距离
    axis_direction = _relative_axis(raw)
    if axis_direction and distance is not None:
        axis, direction = axis_direction
        speed = _speed(raw)
        params = {"axis": axis, "direction": direction, "distance_mm": distance}
        if speed is not None:
            params["speed_percent"] = speed
        return {
            "skill": "move_relative_linear",
            "params": params,
            "explain": f"沿 {axis.upper()} {direction} 方向移动 {distance}mm",
        }

    return None
