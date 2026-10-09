#!/usr/bin/env python3
"""Package only the PostgreSQL tools this gateway uses, without GIS/Python add-ons."""
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent / ".build"
source = root / "bundle/postgres"
target = root / "postgres-minimal"
if target.exists() or (root / "postgres-full").exists():
    raise SystemExit("PostgreSQL has already been packaged")
target.mkdir()
pending = [source / "bin" / name for name in ("postgres", "initdb", "pg_ctl", "psql", "pg_dump", "pg_restore", "pg_isready", "pg_controldata")]
pending.append(source / "lib/postgresql/plpgsql.dylib")
pending.append(source / "lib/postgresql/dict_snowball.dylib")
seen = set()
while pending:
    path = pending.pop()
    if path in seen:
        continue
    seen.add(path)
    relative = path.relative_to(source)
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        destination.symlink_to(path.readlink())
        pending.append(path.resolve())
        continue
    shutil.copy2(path, destination)
    output = subprocess.run(["/usr/bin/otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
    ids = subprocess.run(["/usr/bin/otool", "-D", str(path)], capture_output=True, text=True, check=True).stdout
    identifiers = {line.strip() for line in ids.splitlines() if line and not line.endswith(":")}
    for dependency in {line.strip().split(" (", 1)[0] for line in output.splitlines() if line.startswith("\t")}:
        if dependency in identifiers or dependency.startswith(("/usr/lib/", "/System/Library/")):
            continue
        if dependency.startswith("@loader_path/"):
            resolved = path.parent / dependency.removeprefix("@loader_path/")
        elif dependency.startswith("@rpath/"):
            resolved = source / "lib" / dependency.removeprefix("@rpath/")
        else:
            raise RuntimeError("Unexpected PostgreSQL dependency: " + dependency)
        resolved = Path(__import__("os").path.normpath(resolved))
        if not resolved.is_relative_to(source) or not resolved.exists():
            raise RuntimeError("Missing bundled PostgreSQL dependency")
        pending.append(resolved)
# Preserve initialization data, timezone/tsearch resources, and standard PL/pgSQL.
shutil.copytree(source / "share/postgresql", target / "share/postgresql")
source.rename(root / "postgres-full")
target.rename(source)
print(f"Packaged {len(seen)} PostgreSQL executable/library files; omitted unused GIS and external Python integrations.")
