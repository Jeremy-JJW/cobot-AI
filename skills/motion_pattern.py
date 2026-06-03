import math


PATTERN_NAMES = [
    "circle_xy",
    "circle_xz",
    "circle_yz",
    "arc_xy",
    "arc_xz",
    "arc_yz",
    "square_xy",
    "rectangle_xy",
    "triangle_xy",
    "diamond_xy",
    "cross_xy",
    "zigzag_x",
    "wave_y",
    "u_shape_xy",
    "xyz_step_return",
    "xz_lift_return",
    "yz_lift_return",
    "l_shape_xyz",
    "box_outline",
    "spiral_z",
]


def _pose(base: list[float], dx: float = 0, dy: float = 0, dz: float = 0) -> list[float]:
    pose = list(base)
    pose[0] += dx
    pose[1] += dy
    pose[2] += dz
    return pose


def _run_lines(session, base: list[float], offsets: list[tuple[float, float, float]], speed: int) -> None:
    for dx, dy, dz in offsets:
        session.movl(_pose(base, dx, dy, dz), v=speed)


def _circle_points(base: list[float], radius: float, plane: str) -> tuple[list[float], list[float]]:
    if plane == "xy":
        return _pose(base, radius, radius, 0), _pose(base, radius * 2, 0, 0)
    if plane == "xz":
        return _pose(base, radius, 0, radius), _pose(base, radius * 2, 0, 0)
    if plane == "yz":
        return _pose(base, 0, radius, radius), _pose(base, 0, radius * 2, 0)
    raise ValueError(f"不支持的平面: {plane}")


def _run_spiral(session, base: list[float], radius: float, height: float, turns: int, speed: int) -> None:
    steps = max(12, int(turns) * 12)
    for index in range(steps + 1):
        angle = math.tau * turns * index / steps
        z = height * index / steps
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        session.movl(_pose(base, x, y, z), v=speed)


def run(session, params: dict, context: dict) -> None:
    pattern = params["pattern"]
    size = float(params.get("size_mm", 50))
    radius = float(params.get("radius_mm", min(size, 50)))
    height = float(params.get("height_mm", size))
    turns = int(params.get("turns", 2))
    speed = int(params.get("speed_percent", 30))

    base = session.get_pose()

    if pattern.startswith("circle_"):
        through, end = _circle_points(base, radius, pattern[-2:])
        session.circle(through, end, count=1, v=speed)
        return

    if pattern.startswith("arc_"):
        through, end = _circle_points(base, radius, pattern[-2:])
        session.arc(through, end, v=speed)
        return

    routes = {
        "square_xy": [(size, 0, 0), (size, size, 0), (0, size, 0), (0, 0, 0)],
        "rectangle_xy": [(size, 0, 0), (size, size / 2, 0), (0, size / 2, 0), (0, 0, 0)],
        "triangle_xy": [(size, 0, 0), (size / 2, size, 0), (0, 0, 0)],
        "diamond_xy": [(size / 2, size / 2, 0), (size, 0, 0), (size / 2, -size / 2, 0), (0, 0, 0)],
        "cross_xy": [(size, 0, 0), (-size, 0, 0), (0, 0, 0), (0, size, 0), (0, -size, 0), (0, 0, 0)],
        "zigzag_x": [
            (size / 3, size / 3, 0),
            (size * 2 / 3, -size / 3, 0),
            (size, size / 3, 0),
            (size * 4 / 3, -size / 3, 0),
            (0, 0, 0),
        ],
        "wave_y": [
            (size / 4, size / 4, 0),
            (size / 2, -size / 4, 0),
            (size * 3 / 4, size / 4, 0),
            (size, 0, 0),
            (0, 0, 0),
        ],
        "u_shape_xy": [(0, size, 0), (size, size, 0), (size, 0, 0), (0, 0, 0)],
        "xyz_step_return": [(size, 0, 0), (size, size, 0), (size, size, height), (0, 0, 0)],
        "xz_lift_return": [(size, 0, 0), (size, 0, height), (0, 0, height), (0, 0, 0)],
        "yz_lift_return": [(0, size, 0), (0, size, height), (0, 0, height), (0, 0, 0)],
        "l_shape_xyz": [(size, 0, 0), (size, size, 0), (size, size, height)],
        "box_outline": [
            (size, 0, 0),
            (size, size, 0),
            (0, size, 0),
            (0, 0, 0),
            (0, 0, height),
            (size, 0, height),
            (size, size, height),
            (0, size, height),
            (0, 0, height),
            (0, 0, 0),
        ],
    }

    if pattern == "spiral_z":
        _run_spiral(session, base, radius, height, turns, speed)
        return

    if pattern not in routes:
        raise ValueError(f"未實現的運動路線: {pattern}")
    _run_lines(session, base, routes[pattern], speed)
