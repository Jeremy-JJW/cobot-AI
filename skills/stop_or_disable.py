def run(session, params: dict, context: dict) -> None:
    action = params.get("action", "stop")
    if action == "disable":
        session.disable()
    else:
        session.stop()
