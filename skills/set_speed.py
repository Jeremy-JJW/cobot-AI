def run(session, params: dict, context: dict) -> None:
    session.set_speed(int(params["speed_percent"]))
