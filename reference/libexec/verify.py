#!/usr/bin/env python3
"""Protected installation verification; outputs results, never credentials."""
import importlib.util
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
spec = importlib.util.spec_from_file_location("admin", Path(__file__).with_name("admin.py"))
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
import psycopg

def verify():
    settings = json.loads((runtime.BASE / "installation.json").read_text())
    user = pwd.getpwnam(settings["user"])
    service = pwd.getpwnam("_litellm")
    def normal_user():
        os.initgroups(user.pw_name, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    def service_user():
        os.setgroups([service.pw_gid])
        os.setgid(service.pw_gid)
        os.setuid(service.pw_uid)
    python = str(runtime.RUNTIME / "python/bin/python3.12")
    for name in ("secrets/bootstrap.json", "state/postgres", "logs", "backups"):
        path = str(runtime.BASE / name)
        result = subprocess.run([python, "-I", "-c", "import os,sys; sys.exit(1 if os.access(sys.argv[1],os.R_OK) else 0)", path],
            preexec_fn=normal_user, capture_output=True, env={"PATH": "/usr/bin:/bin"})
        if result.returncode:
            raise RuntimeError("Normal user can access protected data")
    for tree in (runtime.RUNTIME, runtime.BASE / "libexec", runtime.BASE / "config"):
        for root, dirs, files in os.walk(tree):
            for path in [Path(root), *(Path(root) / name for name in dirs + files)]:
                info = path.lstat()
                if info.st_uid != 0 or (not path.is_symlink() and info.st_mode & 0o022):
                    raise RuntimeError("Runtime is not protected against modification")
                if path.is_symlink() and not path.resolve().is_relative_to(runtime.BASE):
                    raise RuntimeError("Runtime symlink escapes installation")
    print("Normal-account access and runtime ownership checks passed.")
    for attempt in range(120):
        try:
            admin.call("/v1/models")
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Gateway readiness timed out")
    env = runtime.environment()
    with psycopg.connect(env["DATABASE_URL"]) as connection:
        role = connection.execute("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()
        if role != (False, False, False):
            raise RuntimeError("Application SQL role has excessive privileges")
    secrets = json.loads(runtime.SECRETS.read_text())
    with psycopg.connect(host="127.0.0.1", port=55432, user="gateway_db_admin",
                         password=secrets["pg_admin_password"], dbname="postgres") as connection:
        if connection.execute("SHOW listen_addresses").fetchone()[0] != "127.0.0.1":
            raise RuntimeError("PostgreSQL is not loopback-only")
        if connection.execute("SHOW unix_socket_directories").fetchone()[0] != "":
            raise RuntimeError("Unexpected PostgreSQL socket")
    try:
        psycopg.connect(host="127.0.0.1", port=55432, user="litellm", password="deliberately-invalid", dbname="litellm", connect_timeout=3)
        raise RuntimeError("Database accepted incorrect credentials")
    except psycopg.OperationalError:
        pass
    print("Database authentication and SQL role restriction checks passed.")
    spec = importlib.util.spec_from_file_location("check_api", runtime.BASE / "libexec/check-api.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    checks.check_api(admin)
    result = subprocess.run([python, "-I", str(runtime.BASE / "libexec/maintenance.py"), "verify"],
        preexec_fn=service_user, env={"PATH": "/usr/bin:/bin"}, capture_output=True)
    if result.returncode:
        raise RuntimeError("Backup/restore verification failed")
    print("Protected backup and restore verification passed.")
    control = str(runtime.BASE / "libexec/control")
    subprocess.run([control, "stop"], check=True, capture_output=True)
    disabled = subprocess.run(["/bin/launchctl", "print-disabled", "system"], check=True, capture_output=True, text=True).stdout
    for label in ("gateway",):
        if not re.search(r'"local\.litellm\.' + label + r'"\s*=>\s*(?:true|disabled)\b', disabled):
            raise RuntimeError("Stop did not persist in launchd's disabled state")
    subprocess.run([control, "start"], check=True, capture_output=True)
    for attempt in range(120):
        try:
            admin.call("/v1/models")
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Gateway did not restart")
    result = subprocess.run(["/usr/local/bin/llm-gateway", "status"], preexec_fn=normal_user,
        env={"PATH": "/usr/bin:/bin"}, capture_output=True)
    if result.returncode:
        raise RuntimeError("Ordinary-user service control is unavailable")
    print("Stop persistence, restart and ordinary-user controls passed.")

if __name__ == "__main__":
    try:
        verify()
    except Exception as error:
        # Report only our fixed messages. Library exceptions may expose URLs.
        message = str(error) if type(error) is RuntimeError else type(error).__name__
        sys.exit("Verification stopped: " + message)
