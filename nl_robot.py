"""
自然语言控制机械臂 — 入口脚本

默认使用规则解析（快速、无需 API Key）。
可选 --llm 作为复杂话术兜底。

用法:
  .venv\\Scripts\\python nl_robot.py --dry-run "向 Z 正方向移动 100 毫米"
  .venv\\Scripts\\python nl_robot.py "去 A 点"
  .venv\\Scripts\\python nl_robot.py --llm "复杂指令..."
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

from executor import execute_skill
from robot_session import RobotSession
from rule_parser import parse_text


def _save_plan(plan: dict) -> str:
    out_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(out_dir, exist_ok=True)
    plan_path = os.path.join(out_dir, "last_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return plan_path


def _plan_from_text(text: str, use_llm: bool) -> dict:
    plan = parse_text(text)
    if plan is not None:
        plan["source"] = "rule"
        return plan

    if not use_llm:
        raise ValueError(
            "无法识别指令。请使用固定话术，见 使用说明.md；"
            "或加 --llm 使用大模型兜底。"
        )

    from llm_planner import plan_from_text

    llm_plan = plan_from_text(text)
    if "skill" in llm_plan:
        llm_plan["source"] = "llm"
        return llm_plan

    # 兼容旧版 steps 格式，取第一步映射为 skill
    step = llm_plan.get("steps", [{}])[0]
    action = step.get("action", "")
    mapping = {
        "movl_relative": "move_relative_linear",
        "movj_relative": "move_relative_linear",
        "movj": "move_to_named_point",
        "movl": "move_to_named_point",
        "speed": "set_speed",
        "sleep": "wait",
    }
    skill = mapping.get(action)
    if not skill:
        raise ValueError(f"大模型返回了未支持的动作: {action}")

    params: dict = {}
    if skill == "move_relative_linear":
        for axis, key in zip("xyz", ("dx", "dy", "dz")):
            if key in step:
                params["axis"] = axis
                params["direction"] = "+" if float(step[key]) >= 0 else "-"
                params["distance_mm"] = abs(float(step[key]))
                break
    elif skill == "move_to_named_point" and "point" in step:
        params["point"] = step["point"]
    elif skill == "set_speed":
        params["speed_percent"] = step.get("percent", 30)
    elif skill == "wait":
        params["seconds"] = step.get("seconds", 1)

    return {
        "skill": skill,
        "params": params,
        "explain": llm_plan.get("explain", text),
        "source": "llm",
    }


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="自然语言控制 Dobot（Skill 架构）")
    parser.add_argument("command", nargs="?", help="一条自然语言指令；省略则进入交互模式")
    parser.add_argument("--dry-run", action="store_true", help="只解析并打印，不连接机械臂")
    parser.add_argument("--llm", action="store_true", help="规则无法识别时使用大模型")
    parser.add_argument("--ip", default=os.environ.get("ROBOT_IP", "192.168.5.1"))
    args = parser.parse_args()

    def run_once(text: str, session: RobotSession | None = None, *, keep_alive: bool = False) -> RobotSession | None:
        print(f"\n用户: {text}")
        plan = _plan_from_text(text, args.llm)
        print("计划:", json.dumps(plan, ensure_ascii=False, indent=2))
        print(f"解析来源: {plan.get('source', 'unknown')}")
        plan_path = _save_plan(plan)
        print(f"已保存: {plan_path}")

        if args.dry_run:
            execute_skill(None, plan, dry_run=True)
            return session

        first_connect = session is None
        if session is None:
            session = RobotSession(args.ip)
            print(f"连接机械臂 {args.ip} ...")
            session.connect()

        if plan["skill"] != "stop_or_disable" or plan["params"].get("action") != "disable":
            session.enable()
            print("使能成功，开始执行" if first_connect else "开始执行")
        execute_skill(session, plan, dry_run=False)
        print("执行完成")

        if keep_alive:
            return session

        session.disconnect()
        return None

    if args.command:
        run_once(args.command)
        return

    print("自然语言机械臂控制（规则优先，输入 quit 退出）")
    session: RobotSession | None = None
    try:
        while True:
            try:
                text = input("\n指令> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text.lower() in {"quit", "exit", "q"}:
                break
            try:
                session = run_once(text, session, keep_alive=True)
            except ValueError as exc:
                print(f"错误: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"错误: {exc}", file=sys.stderr)
                if session is not None:
                    try:
                        session.disconnect()
                    except Exception:
                        pass
                    session = None
    finally:
        if session is not None:
            session.disconnect()


if __name__ == "__main__":
    main()
