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
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.ConnectionError:
        raise RuntimeError(
            "无法连接到 AI 模型服务，请检查网络连接和 API 地址配置"
        ) from None
    except requests.Timeout:
        raise RuntimeError(
            "AI 模型服务响应超时（30 秒），请稍后重试，"
            "或检查 OPENAI_BASE_URL 和 OPENAI_MODEL 配置"
        ) from None
    except requests.RequestException as exc:
        raise RuntimeError(f"AI 模型服务请求异常: {exc}") from exc

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = resp.status_code
        if status == 401:
            raise RuntimeError("AI 模型 API 密钥认证失败，请检查 OPENAI_API_KEY") from exc
        if status == 429:
            raise RuntimeError("AI 模型服务请求太频繁，请稍后重试") from exc
        if 500 <= status < 600:
            raise RuntimeError(f"AI 模型服务暂时不可用（HTTP {status}），请稍后重试") from exc
        raise RuntimeError(f"AI 模型服务返回错误（HTTP {status}）: {resp.text[:200]}") from exc

    try:
        body = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 模型服务返回了无法解析的响应: {resp.text[:200]}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"AI 模型服务返回格式异常: {str(body)[:200]}") from exc

    try:
        plan = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 模型返回了无法解析的 JSON: {content[:300]}") from exc
    if "skill" in plan:
        if not plan.get("skill"):
            raise ValueError(f"模型无法识别指令: {plan.get('explain', content)}")
        return plan
    if "steps" not in plan:
        raise ValueError(f"模型返回格式错误: {content}")
    return plan
