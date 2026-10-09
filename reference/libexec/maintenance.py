#!/usr/bin/env python3
"""One manual protected backup and verified restoration for this cluster."""
import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

def admin_connection():
    import psycopg
    secrets = json.loads(runtime.SECRETS.read_text())
    connection = psycopg.connect(host="127.0.0.1", port=55432, user="gateway_db_admin",
        password=secrets["pg_admin_password"], dbname="postgres", autocommit=True)
    actual = connection.execute("SHOW data_directory").fetchone()[0]
    if Path(actual).resolve() != (runtime.STATE / "postgres").resolve():
        connection.close()
        raise RuntimeError("Refusing to operate on an unexpected PostgreSQL cluster")
    return connection

def backup(verify=False):
    root = runtime.BASE / "backups"
    final = root / "latest.tar.gz"
    # Serialize manual invocations. Build and verify privately before replacing
    # the saved snapshot, so a failure preserves the previous usable backup.
    with (root / ".backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix=".backup-", dir=root) as scratch:
            pending = Path(scratch) / "snapshot"
            pending.mkdir(mode=0o700)
            values = json.loads(runtime.SECRETS.read_text())
            env = runtime.environment(False)
            env["PGPASSWORD"] = values["pg_app_password"]
            command = [str(runtime.RUNTIME / "postgres/bin/pg_dump"), "-h", "127.0.0.1", "-p", "55432",
                "-U", "litellm", "-d", "litellm", "--format=custom", "--file", str(pending / "database.dump")]
            subprocess.run(command, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            shutil.copyfile(runtime.SECRETS, pending / "bootstrap.json")
            shutil.copyfile(runtime.BASE / "config/gateway.yaml", pending / "gateway.yaml")
            shutil.copyfile(runtime.BASE / "installation.json", pending / "installation.json")
            temporary = Path(scratch) / "latest.tar.gz"
            with tarfile.open(temporary, "w:gz") as archive:
                archive.add(pending, arcname="snapshot")
            if verify:
                restore_check(temporary)
            temporary.replace(final)
    return final

def restore_check(path):
    import psycopg
    from psycopg import sql
    # Restore into a disposable database on *our* cluster, never over live data.
    name = "gateway_restore_check_" + os.urandom(6).hex()
    scratch = runtime.STATE / "tmp" / name
    scratch.mkdir(mode=0o700)
    admin = admin_connection()
    try:
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise RuntimeError("Unsafe backup entry")
                target = (scratch / member.name).resolve()
                if not target.is_relative_to(scratch.resolve()):
                    raise RuntimeError("Unsafe backup path")
            archive.extractall(scratch, filter="data")
        data = next(scratch.glob("*/database.dump"))
        saved = json.loads(next(scratch.glob("*/bootstrap.json")).read_text())
        current = json.loads(runtime.SECRETS.read_text())
        if saved["environment"]["LITELLM_SALT_KEY"] != current["environment"]["LITELLM_SALT_KEY"]:
            raise RuntimeError("Backup salt does not match this installation")
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER litellm").format(sql.Identifier(name)))
        env = runtime.environment(False)
        env["PGPASSWORD"] = current["pg_app_password"]
        subprocess.run([str(runtime.RUNTIME / "postgres/bin/pg_restore"), "--exit-on-error", "--no-owner",
            "-h", "127.0.0.1", "-p", "55432", "-U", "litellm", "-d", name, str(data)],
            env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with psycopg.connect(host="127.0.0.1", port=55432, user="litellm", password=current["pg_app_password"], dbname=name) as restored:
            count = restored.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]
            if count < 10:
                raise RuntimeError("Restored database is missing the gateway schema")
    finally:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()
        shutil.rmtree(scratch)

if __name__ == "__main__":
    try:
        mode = sys.argv[1:]
        if mode in ([], ["backup"], ["verify"]):
            runtime.configure()
            backup(verify=mode == ["verify"])
            print("Protected backup saved to " + str(runtime.BASE / "backups/latest.tar.gz"))
            if mode == ["verify"]:
                print("Backup restore verification passed.")
        else:
            sys.exit("Usage: maintenance.py backup | verify")
    except Exception:
        # Upstream exceptions can include connection strings. Keep diagnostics
        # local and do not send the credentials to the installation console.
        sys.exit("Maintenance failed; administrator inspection is required.")
