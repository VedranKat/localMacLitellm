#!/usr/bin/env python3
"""Fresh unprivileged process receives only limited keys on stdin."""
import json
import os
import pwd
import sys
from pathlib import Path

if os.geteuid() < 500:
    sys.exit("Client keys must be written as the normal user.")
os.umask(0o077)
target = Path(pwd.getpwuid(os.geteuid()).pw_dir) / ".config/llm-gateway"
target.mkdir(mode=0o700, parents=True, exist_ok=True)
if target.is_symlink():
    sys.exit("Refusing a symlink for the client key directory.")
for client, key in json.load(sys.stdin):
    if client not in ("agents", "promptfoo"):
        sys.exit("Unexpected client name.")
    fd = os.open(target / (client + ".key"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(key + "\n")
