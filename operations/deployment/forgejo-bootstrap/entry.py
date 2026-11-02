import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("closed_forgejo_bootstrap", Path(__file__).with_name("core.py"))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
raise SystemExit(core.main("@OPERATION@", sys.argv[1:]))
