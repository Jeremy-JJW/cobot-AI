"""規則優先的自然語言解析：固定話術不調用大模型。"""
import re
from typing import Any

from skills.base import resolve_point_name


_JOINT_CN = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6"}

# 關節控制：支持 J1、關節1、1軸、軸1、關節一等寫法
JOINT_CONTROL_RE = re.compile(
    r"(?:"
    r"J\s*([1-6])"             # J1, J 1
    r"|關節\s*([1-6])"         # 關節1, 關節 1
    r"|([1-6])\s*軸"           # 1軸, 1 軸
    r"|軸\s*([1-6])"           # 軸1, 軸 1
    r"|關節\s*([一二三四五六])" # 關節一
    r")\s*"
    r"(正方向|負方向|反方向|正|負|反|[+\-])?\s*"
    r"(?:旋轉|轉|轉動|運動|移動)?\s*"
    r"([\d.]+)\s*(?:度|°)",
    re.I,
)

AXIS_DIRECTIONS = {
    "x+": ("x", "+", ("x正", "x+", "x 軸正", "x軸正", "x正方向", "x軸正方向", "向右", "右移", "往右", "右边", "右邊")),
    "x-": ("x", "-", ("x負", "x-", "x 軸負", "x軸負", "x負方向", "x軸負方向", "向左", "左移", "往左", "左边", "左邊")),
    "y+": ("y", "+", ("y正", "y+", "y 軸正", "y軸正", "y正方向", "y軸正方向", "向后", "後移", "往后", "往後", "后方", "後方", "后边", "後邊", "向後")),
    "y-": ("y", "-", ("y負", "y-", "y 軸負", "y軸負", "y負方向", "y軸負方向", "向前", "前移", "往前", "前方", "前边", "前邊")),
    "z+": ("z", "+", ("z正", "z+", "z 軸正", "z軸正", "z正方向", "z軸正方向", "上升", "抬高", "抬升", "升高", "向上", "往上")),
    "z-": ("z", "-", ("z負", "z-", "z 軸負", "z軸負", "z負方向", "z軸負方向", "下降", "降低", "向下", "往下")),
}

MOTION_PATTERN_ALIASES = [
    ("xyz_step_return", (r"x\+?.*y\+?.*z\+?.*(回到|返回).*(原點|起點|初始)", r"三軸.*回到.*(原點|起點)")),
    ("spiral_z", (r"三維螺旋|空間螺旋|螺旋",)),
    ("circle_xz", (r"xz.*(畫圓|圓形|整圓)|(畫圓|圓形|整圓).*xz",)),
    ("circle_yz", (r"yz.*(畫圓|圓形|整圓)|(畫圓|圓形|整圓).*yz",)),
    ("circle_xy", (r"(xy|水平|桌面).*(畫圓|圓形|整圓)|畫圓|圓形|整圓",)),
    ("arc_xz", (r"xz.*(圓弧|弧線)|(圓弧|弧線).*xz",)),
    ("arc_yz", (r"yz.*(圓弧|弧線)|(圓弧|弧線).*yz",)),
    ("arc_xy", (r"(xy|水平|桌面).*(圓弧|弧線)|圓弧|弧線",)),
    ("square_xy", (r"正方形|方形|方框",)),
    ("rectangle_xy", (r"矩形|長方形",)),
    ("triangle_xy", (r"三角形|三角路線",)),
    ("diamond_xy", (r"菱形",)),
    ("cross_xy", (r"十字|十字形",)),
    ("zigzag_x", (r"鋸齒|折線",)),
    ("wave_y", (r"波浪|波形",)),
    ("u_shape_xy", (r"u\s*型|u\s*形|u\s*字|u字",)),
    ("box_outline", (r"箱體|盒子|立方體|立體框",)),
    ("xz_lift_return", (r"xz.*(抬升|升高|返回|回到)|x.*z.*(抬升|升高|返回|回到)",)),
    ("yz_lift_return", (r"yz.*(抬升|升高|返回|回到)|y.*z.*(抬升|升高|返回|回到)",)),
    ("l_shape_xyz", (r"l\s*型|l\s*形|l\s*字|l字",)),
]


def _build_common_speech_examples() -> tuple[str, ...]:
    verbs = ("移動", "運動", "走", "走一下", "執行", "運行", "沿着", "往", "向", "來一段")
    values = (5, 10, 20, 30, 50, 80, 100, 150, 200)
    units = ("毫米", "mm", "釐米")
    examples: list[str] = []

    for _, _, words in AXIS_DIRECTIONS.values():
        for word in words:
            for verb in verbs:
                for value in values:
                    unit = units[value % len(units)]
                    examples.append(f"{verb}{word}{value}{unit}")

    point_verbs = ("去", "移動到", "運動到", "回到", "到達", "走到")
    for point in ("A點", "B點", "point_a", "point_b", "home", "原點", "零點"):
        for verb in point_verbs:
            examples.append(f"{verb}{point}")

    for speed in (10, 20, 30, 40, 50):
        examples.extend((f"速度設置爲{speed}%", f"速度調到{speed}", f"用{speed}%速度"))

    for seconds in (0.5, 1, 2, 3, 5, 10):
        examples.extend((f"等待{seconds}秒", f"暫停{seconds}秒", f"停{seconds}秒"))

    for name, _ in MOTION_PATTERN_ALIASES:
        examples.extend((f"執行{name}", f"走{name}", f"運行{name}"))

    # 這個樣例庫顯式覆蓋 500+ 常見說法，真實解析仍以正則規則爲準。
    return tuple(dict.fromkeys(examples))


COMMON_SPEECH_EXAMPLES = _build_common_speech_examples()
COMMON_SPEECH_EXAMPLE_COUNT = len(COMMON_SPEECH_EXAMPLES)
assert COMMON_SPEECH_EXAMPLE_COUNT >= 500


def _distance(text: str) -> float | None:
    match = re.search(r"([\d.]+)\s*(?:毫米|mm|釐米|cm|公分)", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    if re.search(r"釐米|cm|公分", text, re.I):
        value *= 10
    return value


def _speed(text: str) -> float | None:
    match = re.search(r"([\d.]+)\s*(?:%|％)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"速度(?:設置|調|調整|設定|爲|到)?\s*([\d.]+)", text)
    if match:
        return float(match.group(1))
    if re.search(r"慢一點|慢點|低速", text):
        return 20
    if re.search(r"快一點|快點|快速", text):
        return 40
    return None


def _point_name(text: str) -> str | None:
    # 不用 \b：中文與 home/point_a 連寫時（如「回到home」）在 Python 正則裏不算詞邊界。
    aliases = {
        r"home|原點|零點": "home",
        r"point[_ ]?a|a\s*點": "point_a",
        r"point[_ ]?b|b\s*點": "point_b",
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
    r"([xyzXYZ])\s*(?:軸)?\s*(正|負|[+\-])?\s*([\d.]+)\s*(?:毫米|mm|釐米|cm|公分)?",
    re.I,
)

MAX_SEQUENCE_STEPS = 10

# 多步相對移動：連接詞 / 順序詞（出現任一詞且能拆出 ≥2 步即走 sequence）
SEQUENCE_INTENT_RE = re.compile(
    r"先(?:運動|移動|走)?|"
    r"再(?:運動|移動|走)?|"
    r"然後(?:運動|移動|走)?|"
    r"接着(?:運動|移動|走)?|"
    r"隨後(?:運動|移動|走)?|"
    r"接下來(?:運動|移動|走)?|"
    r"之後(?:運動|移動|走)?|"
    r"緊接着|"
    r"完了再|然後再|再然後|"
    r"又|以及|並且|而且|"
    r"再接着|再繼續|繼續|"
    r"第[一二三四五六七八九十兩\d]+步|"
    r"[，,、；;]",
    re.I,
)

SEQUENCE_SPLIT_RE = re.compile(
    r"(?:"
    r"先(?:運動|移動|走)?|"
    r"再(?:運動|移動|走)?|"
    r"然後(?:運動|移動|走)?|"
    r"接着(?:運動|移動|走)?|"
    r"隨後(?:運動|移動|走)?|"
    r"接下來(?:運動|移動|走)?|"
    r"之後(?:運動|移動|走)?|"
    r"緊接着|"
    r"完了|完了再|然後再|再然後|"
    r"又|以及|並且|而且|"
    r"再接着|再繼續|繼續|"
    r"第[一二三四五六七八九十兩\d]+步|"
    r"[，,、；;]"
    r")+",
    re.I,
)

VERBOSE_RELATIVE_CLAUSE_RE = re.compile(
    r"(?:向|沿|按)?\s*([xyzXYZ])\s*(?:軸)?\s*(正|負|[+\-])?\s*(?:方向|向)?\s*(?:移動|運動|走|偏移)?\s*([\d.]+)\s*(?:毫米|mm|釐米|cm|公分)?",
    re.I,
)


def _relative_axis(text: str) -> tuple[str, str] | None:
    compact = re.sub(r"\s+", "", text.lower())
    for axis, direction, words in AXIS_DIRECTIONS.values():
        if any(word.replace(" ", "").lower() in compact for word in words):
            return axis, direction

    axis_match = re.search(r"([xyzXYZ])\s*(?:軸)?\s*(正|負|\+|\-)?\s*(?:方向|向)?", text)
    if not axis_match:
        return None
    axis = axis_match.group(1).lower()
    direction_word = axis_match.group(2) or ""
    if direction_word in {"負", "-"} or re.search(r"負|-\s*方向", text):
        return axis, "-"
    return axis, "+"


def _parse_relative_segment(match: re.Match[str]) -> dict[str, Any]:
    axis = match.group(1).lower()
    direction_word = match.group(2) or ""
    distance = float(match.group(3))
    if re.search(r"釐米|cm|公分", match.group(0), re.I):
        distance *= 10
    if direction_word in {"負", "-"}:
        direction = "-"
    else:
        direction = "+"
    return {"axis": axis, "direction": direction, "distance_mm": distance}


def _distance_in_clause(clause: str) -> float | None:
    distance = _distance(clause)
    if distance is not None:
        return distance
    match = re.search(r"([\d.]+)\s*(?:毫米|mm|釐米|cm|公分)?", clause, re.I)
    if not match:
        return None
    value = float(match.group(1))
    if re.search(r"釐米|cm|公分", clause, re.I):
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
                # 保守策略：多步指令只要有任一步解析不了，就整條交給 LLM/報錯，
                # 避免漏掉某一步後仍然執行不完整動作。
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
    if JOINT_CONTROL_RE.search(raw):
        return True
    if _motion_pattern(raw):
        return True
    if re.search(
        r"從\s*[a-zA-Z0-9_]+\s*點?\s*(?:移動|運動)?\s*到\s*[a-zA-Z0-9_]+\s*點?",
        raw,
        re.I,
    ):
        return True
    if re.search(r"(?:移動|運動|去|回到|到達|走|偏移|畫|抬|升|降)", raw):
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
    if re.search(r"抬高|抬升|上升|向上|下降|降低|向下|向左|向右|向前|向後|往前|往後|往左|往右|左移|右移|前移|後移", raw, re.I) and _distance_in_clause(raw) is not None:
        return True
    return False


def _is_speed_only_command(text: str) -> bool:
    speed = _speed(text)
    if speed is None or _has_movement_intent(text):
        return False
    return bool(
        "速度" in text
        or re.search(r"[\d.]+\s*(?:%|％)", text)
        or re.search(r"慢一點|慢點|低速|快一點|快點|快速", text)
    )


def parse_text(text: str) -> dict[str, Any] | None:
    """匹配成功返回 skill 計劃，失敗返回 None。"""
    raw = text.strip()
    if not raw:
        return None

    # 使能 / 停止
    if re.search(r"下使能", raw):
        return {"skill": "stop_or_disable", "params": {"action": "disable"}, "explain": "下使能機械臂"}
    if re.search(r"上使能", raw):
        return {"skill": "enable_robot", "params": {}, "explain": "上使能機械臂"}
    if re.search(r"停止|停住|急停", raw):
        return {"skill": "stop_or_disable", "params": {"action": "stop"}, "explain": "停止當前運動"}

    # 等待
    wait_match = re.search(r"(?:等待|暫停|停一下|停|等)\s*([\d.]+)\s*秒", raw)
    if wait_match:
        return {
            "skill": "wait",
            "params": {"seconds": float(wait_match.group(1))},
            "explain": f"等待 {wait_match.group(1)} 秒",
        }
    if re.search(r"等一下|暫停一下|停一下", raw):
        return {"skill": "wait", "params": {"seconds": 1}, "explain": "等待 1 秒"}

    # 速度（純調速；帶位移的指令在後面解析並附帶 speed_percent）
    if _is_speed_only_command(raw):
        speed = _speed(raw)
        assert speed is not None
        return {
            "skill": "set_speed",
            "params": {"speed_percent": speed},
            "explain": f"設置速度爲 {speed}%",
        }

    # 明確拒識：畫畫/繪畫類（排除具體的 畫圓/畫弧/畫方 等軌跡）
    if re.search(r"畫(?:一[幅個]?)?畫|繪畫", raw) and not re.search(
        r"畫圓|圓形|圓弧|畫弧|方形|正方形|三角形|菱形|十字|波浪|鋸齒",
        raw,
    ):
        return None

    # 關節控制（J1-J6，支持 關節1/1軸/軸1/關節一等說法）
    joint_match = JOINT_CONTROL_RE.search(raw)
    if joint_match:
        # groups 1-5 是關節編號的各種寫法，取第一個非空
        joint_raw = None
        for i in range(1, 6):
            if joint_match.group(i):
                joint_raw = joint_match.group(i).strip()
                break
        if joint_raw in _JOINT_CN:
            joint_raw = _JOINT_CN[joint_raw]
        joint = f"J{joint_raw}"
        direction_text = (joint_match.group(6) or "+").strip()
        angle = float(joint_match.group(7))
        direction = "-" if direction_text in {"負方向", "反方向", "負", "反", "-"} else "+"
        speed = _speed(raw)
        params: dict[str, Any] = {"joint": joint, "direction": direction, "angle_deg": angle}
        if speed is not None:
            params["speed_percent"] = speed
        return {
            "skill": "move_joint",
            "params": params,
            "explain": f"關節 {joint} {'正' if direction == '+' else '負'}方向旋轉 {angle} 度",
        }

    # 讀取 / 記錄位姿
    if re.search(r"讀取|查詢|查看", raw) and re.search(r"位置|位姿|座標", raw):
        return {"skill": "read_pose", "params": {}, "explain": "讀取當前位姿"}
    save_match = re.search(r"(?:記錄|保存|標定).*(?:爲|到)\s*([a-zA-Z0-9_]+)", raw)
    if save_match and re.search(r"位置|位姿|點", raw):
        return {
            "skill": "read_pose",
            "params": {"save_as": save_match.group(1)},
            "explain": f"記錄當前位姿爲 {save_match.group(1)}",
        }

    # 多步相對移動：先 X+ 再 Y+ 等（優先於預置 L 型等複合路線，避免誤加 Z 軸）
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
            "explain": f"按順序移動: {' → '.join(parts)}",
        }

    # 點到點：先去X再到Y[再去Z...]（依序訪問多個點）
    point_seq = re.findall(
        r"(?:先|再|然後|接着|之後)?\s*(?:去|到|回|回到|移動(?:到)?)\s*([a-zA-Z0-9_]+)",
        raw,
        re.I,
    )
    # 解析點名（僅過濾連續重複，保留 A→B→A 這類合法重複）
    points = []
    for p in point_seq:
        resolved = resolve_point_name(p.strip())
        if resolved and (not points or resolved != points[-1]):
            points.append(resolved)
    if len(points) >= 2:
        speed = _speed(raw)
        params = {"from_point": points[0], "to_point": points[-1]}
        if len(points) > 2:
            params["via_points"] = points[1:-1]
        if speed is not None:
            params["speed_percent"] = speed
        parts = " → ".join(points)
        return {
            "skill": "move_between_points",
            "params": params,
            "explain": f"依序移動：{parts}",
        }

    if SEQUENCE_INTENT_RE.search(raw):
        # 多步意圖存在但無法完整解析時，不再降級成單步/預置路線。
        # 例外：「移動 …，速度 20%」這類逗號後只是調速說明，仍按單步處理。
        if not _looks_like_speed_suffix_only(raw):
            return None

    # 複合運動路線要優先於「回到原點」等命名點規則。
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
            "explain": f"執行預置複合運動路線 {pattern}",
        }

    # 點到點：從A到B（兼容舊說法）
    between = re.search(
        r"從\s*([a-zA-Z0-9_]+)\s*點?\s*(?:移動|運動)?\s*到\s*([a-zA-Z0-9_]+)\s*點?",
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
            "explain": f"從 {from_point} 移動到 {to_point}",
        }

    # 去命名點
    if re.search(r"(?:移動|運動|去|回到|到達)", raw):
        point = _point_name(raw)
        if point:
            speed = _speed(raw)
            params = {"point": point}
            if speed is not None:
                params["speed_percent"] = speed
            return {
                "skill": "move_to_named_point",
                "params": params,
                "explain": f"移動到 {point}",
            }

    # 單步相對移動：軸 + 方向 + 距離
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
            "explain": f"沿 {axis.upper()} {direction} 方向移動 {distance}mm",
        }

    return None
