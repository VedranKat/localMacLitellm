#!/usr/bin/env python3
# Called by the fixed shell launcher; imports only the protected packages.
import runpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runtime/packages"))
runpy.run_module("prisma", run_name="__main__")
