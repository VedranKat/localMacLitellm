#!/usr/bin/env python3
"""Human-only administration; requires an actual sudo password (no sudoers grant)."""
import importlib.util
import json
import os
import pwd
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

def call(path, data=None, key=None):
    if key is None:
        key = json.loads(runtime.SECRETS.read_text())["environment"]["LITELLM_MASTER_KEY"]
    request = urllib.request.Request("http://127.0.0.1:4000" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Deliberately do not print upstream response bodies or request payloads.
        raise RuntimeError(f"Gateway administration returned HTTP {error.code}") from None

def invite():
    # Invitation rows reference the creator in UserTable. The master-key
    # authentication path supplies this identity without creating its DB row.
    # With environment UI login disabled, persist the identity without a password
    # or virtual key so the invitation's foreign-key references can resolve.
    try:
        call("/user/info?user_id=default_user_id")
    except RuntimeError as error:
        if str(error) != "Gateway administration returned HTTP 404":
            raise
        call("/user/new", {"user_id": "default_user_id", "user_alias": "Bootstrap administrator",
                           "user_role": "proxy_admin", "auto_create_key": False})
    user = "local-dashboard-admin"
    try:
        call("/user/new", {"user_id": user, "user_alias": "Local administrator", "user_email": "admin@litellm.local",
                           "user_role": "proxy_admin", "auto_create_key": False})
    except RuntimeError:
        # A repeat invocation reuses the existing account, checked independently.
        existing = call("/user/info?user_id=" + user)
        if existing.get("user_info", {}).get("user_role") != "proxy_admin":
            raise
        if not existing["user_info"].get("user_email"):
            call("/user/update", {"user_id": user, "user_email": "admin@litellm.local"})
    result = call("/invitation/new", {"user_id": user})
    token = result["id"]
    url = "http://127.0.0.1:4000/ui/onboarding?invitation_id=" + token
    uid = int(os.environ.get("SUDO_UID", "-1"))
    if uid < 500:
        raise RuntimeError("Run this command from your own terminal with sudo")
    # The one-time link is handed directly to the user's browser, never printed.
    subprocess.run(["/bin/launchctl", "asuser", str(uid), "/usr/bin/sudo", "-u", pwd.getpwuid(uid).pw_name,
                    "/usr/bin/open", url], check=True, stdout=subprocess.DEVNULL)
    print("A one-time administrator invitation was opened in your browser. Set your dashboard password there.")

def provision_clients(models):
    if not models or any(not model or model == "*" or model == "all-proxy-models" for model in models):
        raise RuntimeError("Name the exact configured model aliases to allow")
    available = {item["id"] for item in call("/v1/models")["data"]}
    if not set(models).issubset(available):
        raise RuntimeError("Add these model aliases in the dashboard first")
    uid = int(os.environ.get("SUDO_UID", "-1"))
    if uid < 500:
        raise RuntimeError("Run this command from your own terminal with sudo")
    user = pwd.getpwuid(uid)
    target = Path(user.pw_dir) / ".config/llm-gateway"
    if target.is_symlink() or any((target / (client + ".key")).exists() for client in ("agents", "promptfoo")):
        raise RuntimeError("Client key files already exist; rotate them in the dashboard")
    # Create/write credentials *after* dropping root, so a user-controlled symlink
    # cannot trick an administrator into overwriting privileged files.
    created = []
    for client in ("agents", "promptfoo"):
        owner = "local-client-" + client
        try:
            call("/user/new", {"user_id": owner, "user_role": "internal_user_viewer", "auto_create_key": False})
        except RuntimeError:
            info = call("/user/info?user_id=" + owner)
            if info.get("user_info", {}).get("user_role") != "internal_user_viewer":
                raise
        result = call("/key/generate", {"user_id": owner, "key_alias": client, "models": models,
            "max_budget": 5, "budget_duration": "1d", "rpm_limit": 60, "max_parallel_requests": 4,
            "allowed_routes": ["/v1/chat/completions", "/chat/completions", "/v1/models", "/models"],
            "object_permission": {"mcp_servers": ["no-mcp-servers"]}})
        created.append((client, result["key"]))
    # Exec a fresh unprivileged process rather than demoting this process: root
    # memory has held the master key and must never become readable by agents.
    subprocess.run(["/usr/bin/sudo", "-u", user.pw_name, str(runtime.RUNTIME / "python/bin/python3.12"),
        "-I", str(runtime.BASE / "libexec/write-clients.py")], input=json.dumps(created).encode(),
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin"})
    print("Limited agents and promptfoo keys saved to ~/.config/llm-gateway (values not printed).")

def backup():
    # Run as the service account, never the caller. Nothing is exported to the
    # normal account and a fresh backup must pass restoration before replacement.
    result = subprocess.run(["/usr/bin/sudo", "-u", "_litellm",
        str(runtime.RUNTIME / "python/bin/python3.12"), "-I",
        str(runtime.BASE / "libexec/maintenance.py"), "verify"],
        env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Backup failed; the previous saved snapshot was not replaced")
    print(result.stdout.strip())

if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("Human administration requires sudo.")
    try:
        if sys.argv[1:] == ["invite"]:
            invite()
        elif sys.argv[1:2] == ["clients"]:
            provision_clients(sys.argv[2:])
        elif sys.argv[1:] == ["backup"]:
            backup()
        else:
            sys.exit("Usage: llm-gateway-admin invite | clients MODEL_ALIAS [MODEL_ALIAS ...] | backup")
    except Exception as error:
        message = str(error) if type(error) is RuntimeError else type(error).__name__
        sys.exit(f"Administration failed: {message}; no secret values were printed.")
