from time import sleep


def run(session, params: dict, context: dict) -> None:
    sleep(float(params["seconds"]))
