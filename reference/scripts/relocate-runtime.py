#!/usr/bin/env python3
"""Make bundled libraries resolve relative to their protected directory."""
import subprocess
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent / ".build/bundle"
magic = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
changed = 0
for path in root.rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    with path.open("rb") as file:
        if file.read(4) not in magic:
            continue
    output = subprocess.run(["/usr/bin/otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
    ids = subprocess.run(["/usr/bin/otool", "-D", str(path)], capture_output=True, text=True, check=True).stdout
    own = {line.strip() for line in ids.splitlines() if line and not line.endswith(":")}
    patched = False
    for dependency in {line.strip().split(" (", 1)[0] for line in output.splitlines() if line.startswith("\t")}:
        if dependency in own or dependency.startswith(("/", "@")):
            continue
        if not (path.parent / dependency).exists():
            raise RuntimeError("Missing relative dependency: " + dependency)
        subprocess.run(["/usr/bin/install_name_tool", "-change", dependency, "@loader_path/" + dependency, str(path)], check=True, capture_output=True)
        patched = True
    commands = subprocess.run(["/usr/bin/otool", "-l", str(path)], capture_output=True, text=True, check=True).stdout
    for old in set(re.findall(r"cmd LC_RPATH\n.*?\n\s*path (.*?) \(offset", commands)):
        if old == "/Applications/Postgres.app/Contents/Versions/16/lib":
            new = "@loader_path/" + os.path.relpath(root / "postgres/lib", path.parent)
            subprocess.run(["/usr/bin/install_name_tool", "-rpath", old, new, str(path)], check=True, capture_output=True)
            patched = True
    if patched:
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(path)], check=True, capture_output=True)
        changed += 1
print(f"Relocated {changed} libraries into the self-contained runtime.")
