"""自然语言 -> 动作 JSON（OpenAI 兼容接口）。"""
import json
import os
from pathlib import Path

import requests

PROMPT_PATH = Path(__file__).with_name("robot_planner_prompt.txt")


def load_named_points() -> dict:
    path = Path(__file__).with_name("positions.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("points", data)


def _build_system_prompt(named_points: dict) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    if named_points:
        base += "\n\n可用命名点位（优先使用 point 字段引用）:\n"
        base += json.dumps(named_points, ensure_ascii=False, indent=2)
    return base


def plan_from_text(user_text: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("请设置环境变量 OPENAI_API_KEY")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    named_points = load_named_points()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _build_system_prompt(named_points)},
            {"role": "user", "content": user_text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    plan = json.loads(content)
    if "skill" in plan:
        if not plan.get("skill"):
            raise ValueError(f"模型无法识别指令: {plan.get('explain', content)}")
        return plan
    if "steps" not in plan:
        raise ValueError(f"模型返回格式错误: {content}")
    return plan
