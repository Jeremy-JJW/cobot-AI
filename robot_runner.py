"""Reusable plan-and-execute flow shared by CLI and future web APIs."""
import json
import os
from typing import Any

from executor import execute_skill
from robot_planner import plan_from_text
from robot_session import RobotSession
from semantic_cache import remember_plan


def save_plan(plan: dict[str, Any]) -> str:
    out_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(out_dir, exist_ok=True)
    plan_path = os.path.join(out_dir, "last_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return plan_path


def run_once(
    text: str,
    *,
    use_llm: bool = False,
    dry_run: bool = False,
    ip: str | None = None,
    session: RobotSession | None = None,
    keep_alive: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    plan = plan_from_text(text, use_llm=use_llm)
    plan_path = save_plan(plan)

    if verbose:
        print(f"\n用戶: {text}")
        print("計劃:", json.dumps(plan, ensure_ascii=False, indent=2))
        print(f"解析來源: {plan.get('source', 'unknown')}")
        print(f"已保存: {plan_path}")

    if dry_run:
        validated = execute_skill(None, plan, dry_run=True)
        remember_plan(text, validated, source=plan.get("source", "unknown"))
        return {
            "plan": plan,
            "validated_plan": validated,
            "plan_path": plan_path,
            "session": session,
            "dry_run": True,
        }

    robot_ip = ip or os.environ.get("ROBOT_IP", "192.168.5.1")
    first_connect = session is None
    created_session = False
    if session is None:
        session = RobotSession(robot_ip)
        created_session = True
        if verbose:
            print(f"連接機械臂 {robot_ip} ...")
        session.connect()

    try:
        if plan["skill"] != "read_pose":
            session.enable()
            if verbose:
                print("使能成功，開始執行" if first_connect else "開始執行")

        validated = execute_skill(session, plan, dry_run=False)
        remember_plan(text, validated, source=plan.get("source", "unknown"))
        if verbose:
            print("執行完成")

        if keep_alive:
            next_session = session
        else:
            session.disconnect()
            next_session = None

        return {
            "plan": plan,
            "validated_plan": validated,
            "plan_path": plan_path,
            "session": next_session,
            "dry_run": False,
        }
    except Exception:
        if created_session or not keep_alive:
            try:
                session.disconnect()
            except Exception:
                pass
        raise


def execute_plan(
    text: str,
    plan: dict[str, Any],
    *,
    ip: str | None = None,
    session: RobotSession | None = None,
    keep_alive: bool = True,
) -> dict[str, Any]:
    """Execute a plan that was already validated via /api/plan."""
    plan_path = save_plan(plan)

    robot_ip = ip or os.environ.get("ROBOT_IP", "192.168.5.1")
    first_connect = session is None
    created_session = False
    if session is None:
        session = RobotSession(robot_ip)
        created_session = True
        session.connect()

    try:
        if plan["skill"] != "read_pose":
            session.enable()

        validated = execute_skill(session, plan, dry_run=False)
        remember_plan(text, validated, source=plan.get("source", "unknown"))

        if keep_alive:
            next_session = session
        else:
            session.disconnect()
            next_session = None

        return {
            "plan": plan,
            "validated_plan": validated,
            "plan_path": plan_path,
            "session": next_session,
            "first_connect": first_connect,
            "dry_run": False,
        }
    except Exception:
        if created_session or not keep_alive:
            try:
                session.disconnect()
            except Exception:
                pass
        raise
