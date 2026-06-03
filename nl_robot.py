"""
自然語言控制機械臂 — 入口腳本

默認啓用規則 + 大模型兜底（需配置 OPENAI_API_KEY）。
加 --no-llm 則僅規則解析，不調用 API。

用法:
  .venv\\Scripts\\python nl_robot.py --dry-run "向 Z 正方向移動 100 毫米"
  .venv\\Scripts\\python nl_robot.py "去 A 點"
  .venv\\Scripts\\python nl_robot.py --no-llm "僅規則解析..."
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from robot_session import RobotSession
from robot_runner import run_once


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="自然語言控制 VA 協作機械臂（Skill 架構）")
    parser.add_argument("command", nargs="?", help="一條自然語言指令；省略則進入交互模式")
    parser.add_argument("--dry-run", action="store_true", help="只解析並打印，不連接機械臂")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="僅規則解析，不使用大模型（默認已啓用 LLM 兜底）",
    )
    parser.add_argument("--ip", default=os.environ.get("ROBOT_IP", "192.168.5.1"))
    args = parser.parse_args()

    def cli_run_once(
        text: str,
        session: RobotSession | None = None,
        *,
        keep_alive: bool = False,
    ) -> RobotSession | None:
        result = run_once(
            text,
            use_llm=not args.no_llm,
            dry_run=args.dry_run,
            ip=args.ip,
            session=session,
            keep_alive=keep_alive,
        )
        return result["session"]

    if args.command:
        try:
            cli_run_once(args.command)
        except ValueError as exc:
            print(f"錯誤: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"錯誤: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    print("自然語言機械臂控制（規則 + LLM，輸入 quit 退出）")
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
                session = cli_run_once(text, session, keep_alive=True)
            except ValueError as exc:
                print(f"錯誤: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"錯誤: {exc}", file=sys.stderr)
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
