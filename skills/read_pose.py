import json
from pathlib import Path

from skills.base import POSITIONS_PATH


def run(session, params: dict, context: dict) -> None:
    pose = session.get_pose()
    print(f"当前位姿: {pose}")

    save_as = params.get("save_as")
    if not save_as:
        return

    data = {"points": {}}
    if POSITIONS_PATH.exists():
        data = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
        if "points" not in data:
            data = {"points": data}

    data["points"][save_as] = pose
    POSITIONS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存到 positions.json -> {save_as}")
