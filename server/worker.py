"""Run with python -m server.worker. Single bounded worker by default."""

import os
import signal
import time
from .storage import init
from .accounts import cleanup as cleanup_accounts
from .upload_queue import initialize, process_one, cleanup


def main():
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if os.environ.get("GABBAPROC_AUTO_INIT", "true") == "true":
        init()
        initialize()
    delay = max(0.05, float(os.environ.get("GABBAPROC_WORKER_DELAY", "0.25")))
    last_cleanup = 0
    while running:
        try:
            processed = process_one()
            if time.monotonic() - last_cleanup > 60:
                cleanup()
                cleanup_accounts()
                last_cleanup = time.monotonic()
        except Exception:
            print("Worker unavailable; retrying shortly", flush=True)
            processed = False
        time.sleep(delay if processed else max(delay, 2))


if __name__ == "__main__":
    main()
