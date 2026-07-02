"""Flask Web demo: natural language robot control UI."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from executor import execute_skill
from logger import log_operation, setup_flask_logger
from lua_exporter import export_lua
from program_runner import run_program
from robot_planner import plan_from_text
from robot_runner import execute_plan, save_plan
from robot_session import RobotSession
from script_parser import parse_instruction
from semantic_cache import remember_plan
from web_plan_format import (
    format_completion_message,
    format_executing_message,
    format_plan_summary,
    format_understood_message,
)

load_dotenv()

PROGRAMS_DIR = Path(__file__).resolve().parent / "programs"
_PROGRAM_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff \-]{0,49}$")

app = Flask(__name__)
_robot_lock = threading.Lock()
_robot_session: RobotSession | None = None
_robot_status = "未連接"
_logger = setup_flask_logger()
                                    

def _set_status(status: str) -> None:
    global _robot_status
    _robot_status = status


def _get_session() -> RobotSession | None:
    return _robot_session


def _store_session(session: RobotSession | None) -> None:
    global _robot_session
    _robot_session = session
    if session is None:
        _set_status("未連接")
    elif _robot_status == "未連接":
        _set_status("已就緒")


@app.get("/")
def index():
    response = app.make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.before_request
def _log_request_start():
    request._start_time = time.time()


@app.after_request
def _log_and_cache(response):
    # Log all API requests (skip static files)
    if request.path.startswith("/api/"):
        duration = int((time.time() - request._start_time) * 1000)
        _logger.info(
            "%s %s → %s (%dms)",
            request.method,
            request.path,
            response.status_code,
            duration,
        )
    # Static file cache control
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.get("/api/status")
def api_status():
    session = _get_session()
    connected = session is not None and session.dashboard is not None
    alarm = False
    robot_mode = -1
    if connected and _robot_status != "執行中":
        try:
            mode_raw = session.get_robot_mode()
            robot_mode = int(mode_raw) if mode_raw is not None else -1
            alarm = bool(robot_mode == 9)
        except Exception:
            pass
    try:
        return jsonify({
            "ok": True,
            "status": str(_robot_status) if _robot_status else "未知",
            "connected": connected,
            "alarm": alarm,
            "robot_mode": robot_mode,
        })
    except Exception:
        return jsonify({
            "ok": True,
            "status": "状态获取异常",
            "connected": connected,
            "alarm": False,
            "robot_mode": -1,
        })


@app.post("/api/plan")
def api_plan():
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "請輸入指令"}), 400

    use_llm = not bool(data.get("no_llm"))
    _set_status("分析中")

    try:
        plan = plan_from_text(text, use_llm=use_llm)
        plan_path = save_plan(plan)
        validated = execute_skill(None, plan, dry_run=True)
        remember_plan(text, validated, source=plan.get("source", "unknown"))
        _set_status("已就緒")
        log_operation(
            user_text=text,
            source=plan.get("source"),
            skill=validated.get("skill"),
            params=validated.get("params"),
            result="planned",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify(
            {
                "ok": True,
                "text": text,
                "plan": plan,
                "validated_plan": validated,
                "plan_path": plan_path,
                "summary": format_plan_summary(validated),
                "message": format_understood_message(validated),
            }
        )
    except ValueError as exc:
        _set_status("錯誤")
        log_operation(
            user_text=text,
            source=None,
            skill=None,
            params=None,
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        _set_status("錯誤")
        log_operation(
            user_text=text,
            source=None,
            skill=None,
            params=None,
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    except Exception as exc:
        _set_status("錯誤")
        log_operation(
            user_text=text,
            source=None,
            skill=None,
            params=None,
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": f"解析失敗: {exc}"}), 500


@app.post("/api/run-once")
def api_run_once():
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    plan = data.get("plan")
    if not text or not isinstance(plan, dict):
        return jsonify({"ok": False, "error": "缺少待執行計劃"}), 400

    ip = data.get("ip") or os.environ.get("ROBOT_IP", "192.168.5.1")
    _set_status("執行中")

    try:
        with _robot_lock:
            result = execute_plan(
                text,
                plan,
                ip=ip,
                session=_get_session(),
                keep_alive=True,
            )
            _store_session(result["session"])
        _set_status("已就緒")
        log_operation(
            user_text=text,
            source=plan.get("source"),
            skill=plan.get("skill"),
            params=plan.get("params"),
            result="success",
            duration_ms=int((time.time() - t0) * 1000),
        )
        validated = result.get("validated_plan") or plan
        return jsonify(
            {
                "ok": True,
                "message": format_completion_message(validated),
                "skill": validated.get("skill"),
                "result": validated.get("result"),
            }
        )
    except ValueError as exc:
        _set_status("錯誤")
        log_operation(
            user_text=text,
            source=plan.get("source"),
            skill=plan.get("skill"),
            params=plan.get("params"),
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        _set_status("錯誤")
        with _robot_lock:
            _store_session(None)
        log_operation(
            user_text=text,
            source=plan.get("source"),
            skill=plan.get("skill"),
            params=plan.get("params"),
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": f"執行失敗: {exc}"}), 500


@app.post("/api/jog/start")
def api_jog_start():
    data = request.get_json(silent=True) or {}
    axis_id = str(data.get("axis_id", "")).strip()
    if not axis_id:
        return jsonify({"ok": False, "error": "缺少 axis_id"}), 400
    ip = data.get("ip") or os.environ.get("ROBOT_IP", "192.168.5.1")
    session = _get_session()
    if session is None:
        session = RobotSession(ip=ip)
        _store_session(session)
    try:
        # 确保已连接
        if session.dashboard is None:
            session.connect()
        session.jog_start(axis_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"点动失败: {e}"}), 400


@app.post("/api/jog/stop")
def api_jog_stop():
    session = _get_session()
    if session and session.dashboard:
        try:
            session.jog_stop()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.post("/api/clear-alarm")
def api_clear_alarm():
    with _robot_lock:
        session = _get_session()
        # 如果 session 斷開或不存在，自動重連
        if session is None or session.dashboard is None:
            ip = os.environ.get("ROBOT_IP", "192.168.5.1")
            try:
                new_session = RobotSession(ip)
                new_session.connect()
                _store_session(new_session)
                session = new_session
            except Exception as exc:
                return jsonify({"ok": False, "error": f"無法連接機械臂: {exc}"}), 400
        try:
            session.clear_alarm()
            _set_status("已就緒")
            return jsonify({"ok": True, "message": "報警已清除"})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": f"清除報警失敗: {exc}"}), 500


@app.post("/api/restart")
def api_restart():
    """重啓 Flask 服務。返回響應後啓動新進程替換當前進程。"""
    _logger.info("收到重啓請求，正在重啓服務...")

    def _do_restart() -> None:
        # 等待響應返回前端後再啓動新進程
        import time as _time
        _time.sleep(0.5)
        try:
            subprocess.Popen(
                [sys.executable, *sys.argv],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except Exception:
            pass
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=False).start()
    return jsonify({"ok": True, "message": "服務正在重啓，請稍候..."})


# ── 脚本编程模式 ──

def _ensure_session() -> RobotSession:
    """返回已连接的 session，必要时自动连接。需在 _robot_lock 内调用。"""
    session = _get_session()
    if session is None or session.dashboard is None:
        ip = os.environ.get("ROBOT_IP", "192.168.5.1")
        session = RobotSession(ip)
        session.connect()
        _store_session(session)
    return session


def _validate_program_name(name: str) -> str:
    name = (name or "").strip()
    if not _PROGRAM_NAME_RE.match(name):
        raise ValueError("程序名稱無效（僅支持中英文/數字/空格/短橫線，1～50 字）")
    return name


def _program_path(name: str) -> Path:
    return PROGRAMS_DIR / f"{name}.json"


@app.post("/api/script/plan")
def api_script_plan():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "請輸入指令"}), 400
    use_llm = not bool(data.get("no_llm"))
    try:
        instructions = parse_instruction(text, use_llm=use_llm)
        return jsonify({"ok": True, "instructions": instructions})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"解析失敗: {exc}"}), 500


@app.post("/api/capture-pose")
def api_capture_pose():
    try:
        with _robot_lock:
            session = _ensure_session()
            session.enable()
            pose = session.get_pose()
        return jsonify({"ok": True, "pose": [round(v, 3) for v in pose]})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"讀取當前位置失敗: {exc}"}), 500


@app.get("/api/programs")
def api_list_programs():
    PROGRAMS_DIR.mkdir(exist_ok=True)
    names = sorted(p.stem for p in PROGRAMS_DIR.glob("*.json"))
    return jsonify({"ok": True, "programs": names})


@app.get("/api/programs/<name>")
def api_get_program(name: str):
    try:
        name = _validate_program_name(name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    path = _program_path(name)
    if not path.exists():
        return jsonify({"ok": False, "error": "程序不存在"}), 404
    return jsonify({"ok": True, "program": json.loads(path.read_text(encoding="utf-8"))})


@app.post("/api/programs/<name>")
def api_save_program(name: str):
    data = request.get_json(silent=True) or {}
    try:
        name = _validate_program_name(name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    overwrite = bool(data.get("overwrite"))
    path = _program_path(name)
    if path.exists() and not overwrite:
        return jsonify({"ok": False, "error": "文件名已存在", "exists": True}), 409

    program = {
        "name": name,
        "points": data.get("points", []),
        "instructions": data.get("instructions", []),
    }
    PROGRAMS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(program, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "message": "已保存", "name": name})


@app.delete("/api/programs/<name>")
def api_delete_program(name: str):
    try:
        name = _validate_program_name(name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    path = _program_path(name)
    if path.exists():
        path.unlink()
    return jsonify({"ok": True, "message": "已刪除"})


@app.post("/api/run-program")
def api_run_program():
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    program = data.get("program")
    if not isinstance(program, dict) or not program.get("instructions"):
        return jsonify({"ok": False, "error": "程序為空，無法運行"}), 400

    _set_status("執行中")
    try:
        with _robot_lock:
            session = _ensure_session()
            session.enable()
            stats = run_program(program, session)
        _set_status("已就緒")
        log_operation(
            user_text=f"運行程序 {program.get('name', '')}",
            source="script",
            skill="run_program",
            params=stats,
            result="success",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({
            "ok": True,
            "message": f"程序執行完成：共 {stats['total']} 行，執行 {stats['executed']} 行，跳過 {stats['skipped']} 行",
            "stats": stats,
        })
    except ValueError as exc:
        _set_status("錯誤")
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        _set_status("錯誤")
        with _robot_lock:
            _store_session(None)
        log_operation(
            user_text=f"運行程序 {program.get('name', '')}",
            source="script",
            skill="run_program",
            params=None,
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": f"執行失敗: {exc}"}), 500


@app.post("/api/export-lua")
def api_export_lua():
    data = request.get_json(silent=True) or {}
    program = data.get("program")
    if not isinstance(program, dict):
        return jsonify({"ok": False, "error": "缺少程序內容"}), 400
    try:
        lua_text = export_lua(program)
        return jsonify({"ok": True, "lua": lua_text, "name": program.get("name", "program")})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"導出失敗: {exc}"}), 500


def main() -> None:
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "5000"))
    debug = os.environ.get("WEB_DEBUG", "0") == "1"
    _logger.info("COBOT AI Web 演示版啓動: http://%s:%s", host, port)
    print(f"COBOT AI Web 演示版: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
