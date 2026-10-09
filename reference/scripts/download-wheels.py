#!/usr/bin/env python3
"""Download only reviewed, hash-pinned wheels; never run package installers as root."""
import concurrent.futures
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent.parent
wheels = json.loads((root / ".build/downloads/wheel-estimate.json").read_text())
destination = root / ".build/wheels"
destination.mkdir(exist_ok=True)
lock = (root / "requirements.lock").read_text()

def fetch(item):
    assert item["sha256"] in lock, f"Wheel absent from lock: {item['name']}"
    path = destination / item["filename"]
    if item["name"] == "litellm" and not path.exists():
        shutil.copyfile(root / ".build/downloads/litellm.whl", path)
    if not path.exists():
        with urllib.request.urlopen(item["url"], timeout=60) as response, path.open("wb") as target:
            shutil.copyfileobj(response, target)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], f"Checksum failed: {item['name']}"
    return path.stat().st_size

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    sizes = list(pool.map(fetch, wheels))
print(f"Verified {len(wheels)} wheels; {sum(sizes) / 1e6:.1f} MB")
