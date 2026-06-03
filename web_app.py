"""Flask Web demo: natural language robot control UI."""
import os
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from executor import execute_skill
from logger import log_operation, setup_flask_logger
from robot_planner import plan_from_text
from robot_runner import execute_plan, save_plan
from robot_session import RobotSession
from semantic_cache import remember_plan
from web_plan_format import (
    format_completion_message,
    format_executing_message,
    format_plan_summary,
    format_understood_message,
)

load_dotenv()

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
    # 執行中時跳過 get_robot_mode，避免因 TCP 忙導致請求卡住
    if connected and _robot_status != "執行中":
        try:
            robot_mode = session.get_robot_mode()
            alarm = robot_mode == 9
        except Exception:
            pass
    return jsonify({
        "ok": True,
        "status": _robot_status,
        "connected": connected,
        "alarm": alarm,
        "robot_mode": robot_mode,
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


def main() -> None:
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "5000"))
    debug = os.environ.get("WEB_DEBUG", "0") == "1"
    _logger.info("COBOT AI Web 演示版啓動: http://%s:%s", host, port)
    print(f"COBOT AI Web 演示版: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
