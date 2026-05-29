"""Flask Web demo: natural language robot control UI."""
import os
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
from web_plan_format import format_plan_summary, format_understood_message

load_dotenv()

app = Flask(__name__)
_robot_lock = threading.Lock()
_robot_session: RobotSession | None = None
_robot_status = "未连接"
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
        _set_status("未连接")
    elif _robot_status == "未连接":
        _set_status("已就绪")


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
    connected = _get_session() is not None and _get_session().dashboard is not None
    return jsonify({"ok": True, "status": _robot_status, "connected": connected})


@app.post("/api/plan")
def api_plan():
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "请输入指令"}), 400

    use_llm = not bool(data.get("no_llm"))
    _set_status("分析中")

    try:
        plan = plan_from_text(text, use_llm=use_llm)
        plan_path = save_plan(plan)
        validated = execute_skill(None, plan, dry_run=True)
        remember_plan(text, validated, source=plan.get("source", "unknown"))
        _set_status("已就绪")
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
        _set_status("错误")
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
        _set_status("错误")
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
        _set_status("错误")
        log_operation(
            user_text=text,
            source=None,
            skill=None,
            params=None,
            result="error",
            error_message=str(exc),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": False, "error": f"解析失败: {exc}"}), 500


@app.post("/api/run-once")
def api_run_once():
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    plan = data.get("plan")
    if not text or not isinstance(plan, dict):
        return jsonify({"ok": False, "error": "缺少待执行计划"}), 400

    ip = data.get("ip") or os.environ.get("ROBOT_IP", "192.168.5.1")
    _set_status("执行中")

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
        _set_status("已就绪")
        log_operation(
            user_text=text,
            source=plan.get("source"),
            skill=plan.get("skill"),
            params=plan.get("params"),
            result="success",
            duration_ms=int((time.time() - t0) * 1000),
        )
        return jsonify({"ok": True, "message": "动作已完成"})
    except ValueError as exc:
        _set_status("错误")
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
        _set_status("错误")
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
        return jsonify({"ok": False, "error": f"执行失败: {exc}"}), 500


def main() -> None:
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "5000"))
    debug = os.environ.get("WEB_DEBUG", "0") == "1"
    _logger.info("COBOT AI Web 演示版启动: http://%s:%s", host, port)
    print(f"COBOT AI Web 演示版: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
