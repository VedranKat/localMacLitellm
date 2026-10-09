#!/usr/bin/env python3
"""Common environment. Never import code from the caller's account."""
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RUNTIME = BASE / "runtime"
STATE = BASE / "state"
SECRETS = BASE / "secrets/bootstrap.json"
sys.path.insert(0, str(RUNTIME / "packages"))

def environment(with_secrets=True):
    values = {
        "HOME": str(STATE / "home"),
        "TMPDIR": str(STATE / "tmp"),
        "PATH": f"{BASE}/libexec:{RUNTIME}/packages/bin:{RUNTIME}/python/bin:{RUNTIME}/node/bin:{RUNTIME}/postgres/bin:/usr/bin:/bin",
        "PYTHONPATH": str(RUNTIME / "packages"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LITELLM_MODE": "PRODUCTION",
        "LITELLM_LOG": "ERROR",
        "NO_DOCS": "True", "NO_REDOC": "True", "NO_OPENAPI": "True",
        "STORE_MODEL_IN_DB": "True",
        "PRISMA_BINARY_CACHE_DIR": str(RUNTIME / "prisma"),
        "PRISMA_QUERY_ENGINE_BINARY": str(RUNTIME / "prisma/node_modules/@prisma/engines/query-engine-darwin-arm64"),
        "PRISMA_SCHEMA_ENGINE_BINARY": str(RUNTIME / "prisma/node_modules/@prisma/engines/schema-engine-darwin-arm64"),
        "PRISMA_USE_GLOBAL_NODE": "true", "PRISMA_USE_NODEJS_BIN": "false",
        "PRISMA_OFFLINE_MODE": "true",
        "NPM_CONFIG_CACHE": str(STATE / "home/.npm"),
        "TIKTOKEN_CACHE_DIR": str(STATE / "home/tiktoken"),
        "TOKENIZERS_PARALLELISM": "false",
        "LANG": "en_US.UTF-8",
    }
    if with_secrets:
        values.update(json.loads(SECRETS.read_text())["environment"])
    return values

def configure():
    os.umask(0o077)
    os.environ.clear()
    os.environ.update(environment())
    os.chdir(STATE / "home")
