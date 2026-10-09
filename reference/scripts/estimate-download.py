#!/usr/bin/env python3
"""Estimate macOS arm64 CPython 3.12 wheel downloads from public PyPI metadata."""
import concurrent.futures
import json
import re
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent.parent
deps = re.findall(r"^([A-Za-z0-9_.-]+)==([^ \\\n]+)", (root / "requirements.lock").read_text(), re.M)

def estimate(item):
    name, version = item
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        meta = json.load(response)
    wheels = []
    for wheel in meta["urls"]:
        if wheel["packagetype"] != "bdist_wheel" or wheel.get("yanked"):
            continue
        filename = wheel["filename"]
        _, py, abi, platform = filename.rsplit("-", 3)
        platform = platform.removesuffix(".whl")
        if not (platform == "any" or ("macosx" in platform and ("arm64" in platform or "universal2" in platform))):
            continue
        accepted = any(tag in ("py3", "py2", "cp312") or (tag.startswith("cp3") and abi == "abi3" and int(tag[2:]) <= 312) for tag in py.split("."))
        if accepted:
            wheels.append(wheel)
    if not wheels:
        raise RuntimeError(f"No compatible wheel for {name}")
    # Prefer a bundled native wheel to a smaller pure-Python fallback (SoundFile
    # otherwise tries loading a user-writable Homebrew library at runtime).
    def rank(item):
        filename = item["filename"]
        _, py, abi, platform = filename.rsplit("-", 3)
        return (2 if "arm64" in platform else 1 if "universal2" in platform else 0,
                2 if "cp312" in py else 1 if abi == "abi3" else 0, -item["size"])
    wheel = max(wheels, key=rank)
    return {"name": name, "version": version, "size": wheel["size"], "filename": wheel["filename"], "url": wheel["url"], "sha256": wheel["digests"]["sha256"]}

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    result = list(pool.map(estimate, deps))
(root / ".build/downloads/wheel-estimate.json").write_text(json.dumps(result, indent=2) + "\n")
print(f"Runtime wheels: {sum(item['size'] for item in result) / 1e6:.1f} MB")
for item in sorted(result, key=lambda item: item["size"], reverse=True)[:8]:
    print(f"  {item['name']}: {item['size'] / 1e6:.1f} MB")
