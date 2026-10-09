#!/usr/bin/env python3
"""Initialize only the dedicated gateway cluster and its app role."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
runtime.configure()
import psycopg
from psycopg import sql

def initialize():
    data = runtime.STATE / "postgres"
    if data.exists():
        raise RuntimeError("Database already exists; refusing reinitialization")
    secrets = json.loads(runtime.SECRETS.read_text())
    password_file = runtime.STATE / "tmp/initdb-password"
    password_file.write_text(secrets["pg_admin_password"] + "\n")
    os.chmod(password_file, 0o600)
    try:
        subprocess.run([str(runtime.RUNTIME / "postgres/bin/initdb"), "-D", str(data), "-U", "gateway_db_admin",
            "--pwfile", str(password_file), "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C", "--no-instructions"],
            env=runtime.environment(False), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    finally:
        password_file.unlink(missing_ok=True)
    with (data / "postgresql.conf").open("a") as config:
        config.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\nunix_socket_directories = ''\n"
            "max_connections = 25\nshared_buffers = '64MB'\nwork_mem = '2MB'\nmaintenance_work_mem = '32MB'\n"
            "password_encryption = 'scram-sha-256'\nlog_statement = 'none'\nlogging_collector = off\n")
    (data / "pg_hba.conf").write_text("host litellm litellm 127.0.0.1/32 scram-sha-256\n"
        "host all gateway_db_admin 127.0.0.1/32 scram-sha-256\n"
        "host all litellm 127.0.0.1/32 scram-sha-256\n"
        "host all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n")
    # The second litellm rule permits only the temporary restore-check databases
    # too; SQL CONNECT privileges on all other databases are revoked below.
    subprocess.run([str(runtime.RUNTIME / "postgres/bin/pg_ctl"), "-D", str(data),
        "-l", str(runtime.BASE / "logs/postgres.log"), "-w", "start"],
        env=runtime.environment(False), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        with psycopg.connect(host="127.0.0.1", port=55432, user="gateway_db_admin", password=secrets["pg_admin_password"],
                             dbname="postgres", autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE ROLE litellm LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}")
                .format(sql.Literal(secrets["pg_app_password"])))
            connection.execute("REVOKE CONNECT ON DATABASE postgres FROM PUBLIC")
            connection.execute("REVOKE CONNECT ON DATABASE template1 FROM PUBLIC")
            connection.execute("CREATE DATABASE litellm OWNER litellm")
            connection.execute("REVOKE ALL ON DATABASE litellm FROM PUBLIC")
        with psycopg.connect(runtime.environment()["DATABASE_URL"]) as connection:
            connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    finally:
        subprocess.run([str(runtime.RUNTIME / "postgres/bin/pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
            env=runtime.environment(False), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print("Dedicated PostgreSQL cluster initialized.")

if __name__ == "__main__":
    try:
        initialize()
    except Exception:
        sys.exit("Database initialization failed; protected diagnostics require administrator review.")
