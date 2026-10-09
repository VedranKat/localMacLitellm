#!/usr/bin/env python3
"""Reject executable dependencies outside the standalone installation bundle."""
import concurrent.futures
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent / ".build/bundle"
magic = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
executables = []
for path in root.rglob("*"):
    if path.is_file() and not path.is_symlink():
        with path.open("rb") as file:
            if file.read(4) in magic:
                executables.append(path)

def inspect(path):
    result = subprocess.run(["/usr/bin/otool", "-L", str(path)], capture_output=True, text=True, check=True)
    ids_result = subprocess.run(["/usr/bin/otool", "-D", str(path)], capture_output=True, text=True, check=True)
    identifiers = {line.strip() for line in ids_result.stdout.splitlines() if line and not line.endswith(":")}
    bad = []
    for line in result.stdout.splitlines():
        if not line.startswith("\t"):
            continue
        dependency = line.strip().split(" (", 1)[0]
        if dependency in identifiers:
            continue  # A library's own install ID is not an imported dependency.
        if dependency.startswith(("/System/Library/", "/usr/lib/", "@loader_path/", "@rpath/", "@executable_path/")):
            continue
        if dependency.startswith(str(root)):
            continue
        bad.append(dependency)
    commands = subprocess.run(["/usr/bin/otool", "-l", str(path)], capture_output=True, text=True, check=True).stdout
    import re
    for rpath in re.findall(r"cmd LC_RPATH\n.*?\n\s*path (.*?) \(offset", commands):
        if not rpath.startswith(("@loader_path", "@executable_path", "/usr/lib", "/System/Library", str(root))):
            bad.append("rpath=" + rpath)
    return (str(path.relative_to(root)), bad)

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(inspect, executables))
failures = [(name, bad) for name, bad in results if bad]
if failures:
    raise SystemExit("External runtime dependencies: " + repr(failures[:10]))
print(f"Audited {len(executables)} native binaries; no absolute dependencies on user-installed runtimes.")
