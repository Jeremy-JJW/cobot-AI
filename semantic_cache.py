"""Local experience store for reusing previously validated robot plans."""
import copy
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

CACHE_PATH = Path(__file__).resolve().parent / "generated" / "experience_cache.json"
CACHE_VERSION = 1
MAX_ENTRIES = 1000
SIMILARITY_THRESHOLD = 0.94

CACHEABLE_SKILLS = {
    "move_relative_linear",
    "move_relative_sequence",
    "move_to_named_point",
    "move_between_points",
    "motion_pattern",
    "set_speed",
    "wait",
}

PUNCTUATION_RE = re.compile(r"[\s，,。；;：:！!？?、]+")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

NORMALIZE_REPLACEMENTS = (
    ("毫米", "mm"),
    ("公分", "cm"),
    ("厘米", "cm"),
    ("％", "%"),
    ("正方向", "+"),
    ("负方向", "-"),
    ("正向", "+"),
    ("负向", "-"),
    ("向x+", "x+"),
    ("向x-", "x-"),
    ("向y+", "y+"),
    ("向y-", "y-"),
    ("向z+", "z+"),
    ("向z-", "z-"),
    ("x轴", "x"),
    ("y轴", "y"),
    ("z轴", "z"),
    ("抬高", "z+"),
    ("上升", "z+"),
    ("向上", "z+"),
    ("下降", "z-"),
    ("降低", "z-"),
    ("向下", "z-"),
    ("a点", "point_a"),
    ("b点", "point_b"),
    ("原点", "home"),
    ("零点", "home"),
    ("长方形", "矩形"),
    ("方框", "方形"),
    ("圆形", "圆"),
    ("弧线", "圆弧"),
    # 繁体中文变体（台湾用）
    ("a點", "point_a"),
    ("b點", "point_b"),
    ("原點", "home"),
    ("零點", "home"),
    ("長方形", "矩形"),
    ("圓形", "圓"),
    ("弧線", "圓弧"),
    ("x軸", "x"),
    ("y軸", "y"),
    ("z軸", "z"),
)

NOISE_WORDS = (
    "请",
    "帮我",
    "让机械臂",
    "机械臂",
    "执行",
    "运行",
    "移动",
    "运动",
    "走一下",
    "走",
    "来一段",
    "一下",
    # 繁体中文变体
    "請",
    "幫我",
    "讓機械臂",
    "機械臂",
    "執行",
    "運行",
    "移動",
    "運動",
    "來一段",
)

PATTERN_WORDS = (
    "圆",
    "圆弧",
    "方形",
    "矩形",
    "三角",
    "菱形",
    "十字",
    "锯齿",
    "波浪",
    "u型",
    "l型",
    "箱体",
    "盒子",
    "螺旋",
    # 繁体中文变体
    "圓",
    "圓弧",
    "方形",
    "矩形",
    "三角",
    "菱形",
    "鋸齒",
    "波浪",
    "箱體",
    "螺旋",
)


def normalize_text(text: str) -> str:
    """Normalize user text enough for exact and conservative fuzzy matches."""
    normalized = text.strip().lower()
    normalized = PUNCTUATION_RE.sub("", normalized)
    for old, new in NORMALIZE_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    for word in NOISE_WORDS:
        normalized = normalized.replace(word, "")
    return normalized


def _load_entries() -> list[dict[str, Any]]:
    if not CACHE_PATH.exists():
        return []
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if data.get("version") != CACHE_VERSION:
        return []
    entries = data.get("entries", [])
    return entries if isinstance(entries, list) else []


def _save_entries(entries: list[dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "entries": entries[-MAX_ENTRIES:],
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(NUMBER_RE.findall(text))


def _direction_tokens(text: str) -> set[str]:
    return {
        token
        for token in ("x+", "x-", "y+", "y-", "z+", "z-")
        if token in text
    }


def _point_tokens(text: str) -> set[str]:
    return {
        token
        for token in ("point_a", "point_b", "home")
        if token in text
    }


def _pattern_tokens(text: str) -> set[str]:
    return {token for token in PATTERN_WORDS if token in text}


def _safe_to_reuse(query_norm: str, entry_norm: str, entry: dict[str, Any]) -> bool:
    plan = entry.get("plan") or {}
    if plan.get("skill") not in CACHEABLE_SKILLS:
        return False
    if _numbers(query_norm) != _numbers(entry_norm):
        return False
    if _direction_tokens(query_norm) != _direction_tokens(entry_norm):
        return False
    if _point_tokens(query_norm) != _point_tokens(entry_norm):
        return False
    if _pattern_tokens(query_norm) != _pattern_tokens(entry_norm):
        return False
    return True


def _copy_plan_from_entry(entry: dict[str, Any], score: float) -> dict[str, Any]:
    plan = copy.deepcopy(entry["plan"])
    plan["source"] = "cache"
    plan["cache_match"] = {
        "text": entry.get("text", ""),
        "score": round(score, 3),
    }
    return plan


def lookup_plan(text: str) -> dict[str, Any] | None:
    """Return a cached plan when text is an exact or very safe semantic match."""
    query_norm = normalize_text(text)
    if not query_norm:
        return None

    entries = _load_entries()
    for entry in reversed(entries):
        entry_norm = entry.get("normalized_text", "")
        if query_norm == entry_norm and (entry.get("plan") or {}).get("skill") in CACHEABLE_SKILLS:
            return _copy_plan_from_entry(entry, 1.0)

    best_entry: dict[str, Any] | None = None
    best_score = 0.0
    for entry in reversed(entries):
        entry_norm = entry.get("normalized_text", "")
        if not entry_norm or not _safe_to_reuse(query_norm, entry_norm, entry):
            continue
        score = SequenceMatcher(None, query_norm, entry_norm).ratio()
        if score > best_score:
            best_entry = entry
            best_score = score

    if best_entry is None or best_score < SIMILARITY_THRESHOLD:
        return None
    return _copy_plan_from_entry(best_entry, best_score)


def remember_plan(text: str, plan: dict[str, Any], source: str = "unknown") -> None:
    """Record a validated plan so future equivalent instructions can skip LLM."""
    skill = plan.get("skill")
    if skill not in CACHEABLE_SKILLS:
        return

    normalized = normalize_text(text)
    if not normalized:
        return

    stored_plan = {
        "skill": skill,
        "params": copy.deepcopy(plan.get("params", {})),
        "explain": plan.get("explain", text),
    }
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    entries = _load_entries()

    for entry in entries:
        if entry.get("normalized_text") == normalized:
            entry["text"] = text
            entry["plan"] = stored_plan
            if source != "cache" or not entry.get("source"):
                entry["source"] = source
            entry["updated_at"] = now
            entry["hit_count"] = int(entry.get("hit_count", 0)) + 1
            _save_entries(entries)
            return

    entries.append(
        {
            "text": text,
            "normalized_text": normalized,
            "plan": stored_plan,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "hit_count": 1,
        }
    )
    _save_entries(entries)
