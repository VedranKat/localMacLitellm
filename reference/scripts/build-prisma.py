#!/usr/bin/env python3
"""Prepare all executable database tooling before sealing the runtime."""
import os
import runpy
import re
import sys
from pathlib import Path

bundle = Path(__file__).resolve().parent.parent / ".build/bundle"
os.environ.update({
    "PATH": f"{bundle}/packages/bin:{bundle}/node/bin:{bundle}/python/bin:/usr/bin:/bin",
    "PYTHONPATH": str(bundle / "packages"),
    "PYTHONNOUSERSITE": "1",
    "PRISMA_BINARY_CACHE_DIR": str(bundle / "prisma"),
    "PRISMA_USE_GLOBAL_NODE": "true",
    "PRISMA_USE_NODEJS_BIN": "false",
    "NPM_CONFIG_CACHE": str(bundle.parent / "npm-cache"),
})
sys.path.insert(0, str(bundle / "packages"))
args = sys.argv[1:]
if args and args[0] == "generate":
    # The upstream schema lists Linux targets too. Generate only the native
    # client so a Mac installation does not download unused Linux engines.
    original = bundle / "packages/litellm_proxy_extras/schema.prisma"
    local = original.with_name("schema.local.prisma")
    local.write_text(re.sub(r"binaryTargets\s*=\s*\[[^\]]+\]", 'binaryTargets = ["native"]', original.read_text()))
    args = ["generate", "--schema", str(local)]
sys.argv = ["prisma", *args]
runpy.run_module("prisma", run_name="__main__")
