def run(session, params: dict, context: dict) -> None:
    session.set_do(int(params["index"]), params["state"])
