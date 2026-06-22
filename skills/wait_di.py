import time


def run(session, params: dict, context: dict) -> None:
    index = int(params["index"])
    want = 1 if str(params["state"]).strip().upper() == "ON" else 0
    timeout = float(params.get("timeout_seconds", 10))
    deadline = time.monotonic() + timeout
    while True:
        if session.read_di(index) == want:
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"等待 DI{index} 為 {params['state']} 超時（{timeout}s）")
        time.sleep(0.05)
