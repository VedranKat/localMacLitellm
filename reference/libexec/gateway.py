#!/usr/bin/env python3
import importlib.util
import shutil
import sys
import threading
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
runtime.configure()

def rotate_logs():
    # Copytruncate preserves launchd's open
    # stdout/stderr descriptors, including this process's gateway log.
    for path in (runtime.BASE / "logs").glob("*.log"):
        if path.stat().st_size > 5 * 1024 * 1024:
            for index in range(3, 0, -1):
                old = path.with_name(path.name + f".{index}")
                if old.exists():
                    if index == 3:
                        old.unlink()
                    else:
                        old.rename(path.with_name(path.name + f".{index+1}"))
            shutil.copyfile(path, path.with_name(path.name + ".1"))
            with path.open("r+") as log:
                log.truncate(0)

def check_logs():
    try:
        rotate_logs()
    except OSError:
        # Optional housekeeping must not prevent model calls.
        print("Log check failed; gateway will continue running.", file=sys.stderr, flush=True)

log_stop = threading.Event()

def log_housekeeping():
    while not log_stop.wait(3600):
        check_logs()

check_logs()
threading.Thread(target=log_housekeeping, name="litellm-log-housekeeping", daemon=True).start()
print("Log checks enabled at startup and hourly inside the gateway.", flush=True)

import psycopg

for attempt in range(30):
    try:
        with psycopg.connect(runtime.environment()["DATABASE_URL"], connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        break
    except psycopg.Error:
        time.sleep(2)
else:
    sys.exit("Gateway waiting for its database; launchd will retry.")

from litellm.proxy.proxy_cli import run_server
sys.argv = ["litellm", "--config", str(runtime.BASE / "config/gateway.yaml"),
            "--host", "127.0.0.1", "--port", "4000", "--num_workers", "1"]
try:
    run_server()
finally:
    log_stop.set()
