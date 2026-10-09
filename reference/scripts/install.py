#!/usr/bin/python3
"""First installation only. Execute with Apple's Python and administrator rights.

Build/download everything unprivileged first. Never runs pip/npm as root, reads
provider credentials, or overwrites development databases and service accounts.
"""
import hashlib
import json
import os
import plistlib
import pwd
import re
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import uuid
from pathlib import Path

BASE = Path("/Library/Application Support/LiteLLM")
SOURCE = Path(__file__).resolve().parent.parent
BUILD = SOURCE / ".build"
ACCOUNT = "_litellm"
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"}

def run(args, **kwargs):
    result = subprocess.run(args, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        # No command in this installer passes secrets on argv. Child helpers
        # intentionally return only fixed, non-secret diagnostic messages.
        raise RuntimeError(Path(args[0]).name + " failed: " + result.stderr.decode(errors="replace")[-1500:].strip())
    return result

def verify_path(path):
    # macOS ACLs can grant access even when POSIX mode bits are restrictive.
    for current in [path, *path.parents]:
        info = current.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("Unsafe parent permissions: " + str(current))
        if subprocess.run(["/bin/ls", "-lde", str(current)], capture_output=True, text=True).stdout.count("\n") > 1:
            raise RuntimeError("Unexpected ACL on protected path: " + str(current))

def account():
    recovery_file = BUILD / "service-account-recovery.json"
    if recovery_file.exists():
        # A narrowly scoped recovery of the account created by this exact install
        # attempt, checked by GUID and all relevant properties. Never adopt an
        # arbitrary existing account just because its name happens to match.
        recovery = json.loads(recovery_file.read_text())
        current = pwd.getpwnam(ACCOUNT)
        guid = run(["/usr/bin/dscl", ".", "-read", "/Users/" + ACCOUNT, "GeneratedUID"]).stdout.decode().split()[-1]
        group = run(["/usr/bin/dscl", ".", "-read", "/Groups/" + ACCOUNT, "PrimaryGroupID"]).stdout.decode().split()[-1]
        memberships = run(["/usr/bin/id", "-Gn", ACCOUNT]).stdout.decode().split()
        if (guid != recovery["guid"] or current.pw_uid != recovery["uid"] or current.pw_gid != recovery["uid"]
            or group != str(recovery["uid"]) or current.pw_shell != "/usr/bin/false"
            or current.pw_dir != str(BASE / "state/home") or "admin" in memberships or "wheel" in memberships):
            raise RuntimeError("Partial-account recovery failed identity checks")
        return current.pw_uid
    for kind in ("Users", "Groups"):
        exists = subprocess.run(["/usr/bin/dscl", ".", "-read", f"/{kind}/{ACCOUNT}"], env=ENV, capture_output=True).returncode == 0
        if exists:
            raise RuntimeError("The service account/group already exists; refusing to adopt it")
    users = run(["/usr/bin/dscl", ".", "-list", "/Users", "UniqueID"]).stdout.decode()
    groups = run(["/usr/bin/dscl", ".", "-list", "/Groups", "PrimaryGroupID"]).stdout.decode()
    taken = {int(line.split()[-1]) for line in (users + groups).splitlines()}
    uid = next(value for value in range(450, 500) if value not in taken)
    run(["/usr/bin/dscl", ".", "-create", "/Groups/" + ACCOUNT])
    run(["/usr/bin/dscl", ".", "-create", "/Groups/" + ACCOUNT, "PrimaryGroupID", str(uid)])
    run(["/usr/bin/dscl", ".", "-create", "/Groups/" + ACCOUNT, "Password", "*"])
    run(["/usr/bin/dscl", ".", "-create", "/Users/" + ACCOUNT])
    fields = {"UniqueID": str(uid), "PrimaryGroupID": str(uid), "RealName": "LiteLLM gateway service",
              "NFSHomeDirectory": str(BASE / "state/home"), "UserShell": "/usr/bin/false",
              "Password": "*", "IsHidden": "1", "GeneratedUID": str(uuid.uuid4()).upper()}
    for key, value in fields.items():
        run(["/usr/bin/dscl", ".", "-create", "/Users/" + ACCOUNT, key, value])
    return uid

def seal(path, uid=0, gid=0, directory_mode=0o755):
    run(["/bin/chmod", "-RN", str(path)])
    for root, directories, files in os.walk(path):
        os.chown(root, uid, gid)
        os.chmod(root, directory_mode)
        for name in directories + files:
            target = Path(root) / name
            if target.is_symlink():
                resolved = target.resolve()
                if not (resolved.is_relative_to(BASE.resolve()) or str(resolved).startswith(("/System/", "/usr/lib/"))):
                    raise RuntimeError("Runtime symlink escapes protected installation: " + str(target))
                os.lchown(target, uid, gid)
            elif target.is_file():
                executable = target.stat().st_mode & 0o111
                os.chown(target, uid, gid)
                os.chmod(target, 0o755 if executable else 0o644)

def launchd(label, arguments, uid, keep_alive=False):
    values = {"Label": label, "ProgramArguments": arguments, "UserName": ACCOUNT, "GroupName": ACCOUNT,
        "WorkingDirectory": str(BASE / "state/home"), "Umask": 0o077,
        "StandardOutPath": str(BASE / "logs" / (label.split(".")[-1] + ".log")),
        "StandardErrorPath": str(BASE / "logs" / (label.split(".")[-1] + ".log")), "ThrottleInterval": 15,
        "ProcessType": "Background", "ExitTimeOut": 75}
    if keep_alive:
        values.update({"RunAtLoad": True, "KeepAlive": True})
    path = Path("/Library/LaunchDaemons") / (label + ".plist")
    if path.exists():
        raise RuntimeError("Launchd job already exists: " + label)
    path.write_bytes(plistlib.dumps(values))
    os.chown(path, 0, 0)
    os.chmod(path, 0o644)

def install():
    if os.geteuid() != 0:
        raise RuntimeError("Installation requires administrator authentication")
    if sys.platform != "darwin":
        raise RuntimeError("This installer targets macOS")
    os.umask(0o077)
    user_name = sys.argv[1] if len(sys.argv) == 2 else os.environ.get("SUDO_USER", "")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user_name):
        raise RuntimeError("Supply the normal macOS account name")
    user = pwd.getpwnam(user_name)
    if user.pw_uid < 500:
        raise RuntimeError("Daily controls must belong to the normal user")
    if BASE.exists():
        raise RuntimeError("Installation already exists; use the documented upgrade procedure")
    verify_path(BASE.parent)
    verify_path(Path("/Library/LaunchDaemons"))
    verify_path(Path("/usr/local/bin"))
    verify_path(Path("/private/etc/sudoers.d"))
    for port in (4000, 55432):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # fail before account creation on collision
    expected = json.loads((BUILD / "bundle-manifest.json").read_text())
    for relative, digest in expected.items():
        path = BUILD / "bundle" / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Installation bundle changed since verification")
    for label in ("postgres", "gateway", "logs", "backup"):
        if Path(f"/Library/LaunchDaemons/local.litellm.{label}.plist").exists():
            raise RuntimeError("A conflicting gateway launchd job exists")
    sudoers = Path("/private/etc/sudoers.d/litellm-gateway")
    if sudoers.exists():
        raise RuntimeError("A conflicting sudoers policy exists")
    for name in ("llm-gateway", "llm-gateway-admin", "llm-call"):
        if Path("/usr/local/bin", name).exists():
            raise RuntimeError("A conflicting client command exists: " + name)
    uid = account()
    BASE.mkdir(mode=0o755)
    shutil.copytree(BUILD / "bundle", BASE / "runtime", symlinks=True)
    for relative, digest in expected.items():
        if hashlib.sha256((BASE / "runtime" / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Installed runtime differs from the verified bundle")
    shutil.copytree(SOURCE / "libexec", BASE / "libexec", ignore=shutil.ignore_patterns("*.c", "__pycache__"))
    shutil.copy2(BUILD / "control", BASE / "libexec/control")
    shutil.copy2(BUILD / "LiteLLM Gateway", BASE / "libexec/LiteLLM Gateway")
    shutil.copytree(SOURCE / "config", BASE / "config")
    seal(BASE)
    # Console-script shebangs created in staging must never refer to that staging
    # interpreter once protected credentials exist.
    entrypoints = BASE / "runtime/packages/.entrypoints"
    entrypoints.mkdir(mode=0o755)
    for path in (BASE / "runtime/packages/bin").glob("*"):
        if path.is_file() and path.read_bytes().startswith(b"#!"):
            text = path.read_text()
            first, _, rest = text.partition("\n")
            if "python" in first:
                script = entrypoints / (path.name + ".py")
                script.write_text("import sys\nsys.path.insert(0, " + repr(str(BASE / "runtime/packages")) + ")\n" + rest)
                os.chmod(script, 0o644)
                path.write_text("#!/bin/sh\nexec " + shlex.quote(str(BASE / "runtime/python/bin/python3.12"))
                    + " -I " + shlex.quote(str(script)) + ' "$@"\n')
                os.chmod(path, 0o755)
    generated = BASE / "runtime/packages/prisma/client.py"
    generated.write_text(generated.read_text().replace(str(BUILD / "bundle"), str(BASE / "runtime")))
    os.chmod(generated, 0o644)
    prisma = BASE / "libexec/prisma"
    os.chmod(prisma, 0o755)
    for directory in ("secrets", "state", "logs", "backups"):
        path = BASE / directory
        path.mkdir(mode=0o700)
        os.chown(path, uid, uid)
    for directory in ("home", "tmp"):
        path = BASE / "state" / directory
        path.mkdir(mode=0o700)
        os.chown(path, uid, uid)
    values = {"pg_admin_password": secrets.token_urlsafe(40), "pg_app_password": secrets.token_urlsafe(40)}
    values["environment"] = {"LITELLM_MASTER_KEY": "sk-" + secrets.token_urlsafe(48), "LITELLM_SALT_KEY": secrets.token_urlsafe(48),
        "DATABASE_URL": "postgresql://litellm:" + values["pg_app_password"] + "@127.0.0.1:55432/litellm"}
    bootstrap = BASE / "secrets/bootstrap.json"
    bootstrap.write_text(json.dumps(values) + "\n")
    os.chown(bootstrap, 0, uid)
    os.chmod(bootstrap, 0o640)
    # The directory permits the service to read but not replace bootstrap secrets.
    os.chown(BASE / "secrets", 0, uid)
    os.chmod(BASE / "secrets", 0o750)
    (BASE / "installation.json").write_text(json.dumps({"litellm": "1.104.0", "python": "3.12.15",
        "postgresql": "16.15", "node": "22.23.3", "user": user_name, "service_uid": uid}, indent=2) + "\n")
    os.chmod(BASE / "installation.json", 0o644)
    python = str(BASE / "runtime/python/bin/python3.12")
    initialize = ["/usr/bin/sudo", "-u", ACCOUNT, python, "-I", str(BASE / "libexec/initialize.py")]
    run(initialize)
    launchd("local.litellm.gateway", [str(BASE / "libexec/LiteLLM Gateway")], uid, True)
    for name in ("llm-gateway", "llm-gateway-admin", "llm-call"):
        path = Path("/usr/local/bin", name)
        shutil.copy2(SOURCE / "bin" / name, path)
        os.chown(path, 0, 0)
        os.chmod(path, 0o755)
    # Escape the command path; exact arguments are required, no wildcard or bare
    # launchctl/python command is granted. Human admin tool has no NOPASSWD entry.
    control_path = str(BASE / "libexec/control").replace(" ", "\\ ")
    commands = ', '.join(control_path + " " + action for action in ("start", "stop", "restart", "status"))
    sudoers.write_text(f"{user_name} ALL=(root) NOPASSWD: {commands}\n")
    os.chown(sudoers, 0, 0)
    os.chmod(sudoers, 0o440)
    try:
        run(["/usr/sbin/visudo", "-cf", str(sudoers)])
    except Exception:
        sudoers.unlink()
        raise
    run([str(BASE / "libexec/control"), "start"])
    print("Protected LiteLLM services installed and started. No provider keys have been configured.")
    verification = run([python, "-I", str(BASE / "libexec/verify.py")])
    print(verification.stdout.decode().strip())
    ENV["SUDO_UID"] = str(user.pw_uid)
    invitation = run([python, "-I", str(BASE / "libexec/admin.py"), "invite"])
    print(invitation.stdout.decode().strip())

if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        # Suppress subprocess payloads, which may contain passwords in SQL/URLs.
        message = str(error) if isinstance(error, (RuntimeError, OSError)) else type(error).__name__
        sys.exit("Installation stopped: " + message)
