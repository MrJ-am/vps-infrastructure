"""Unprivileged collector, called only by the immutable transient-unit launcher."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parent
sys.path.insert(0, str(ROOT))
from bounded import Refused, run

ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "PATH": "/no-path"}


def main():
    try:
        if len(sys.argv) != 1 or os.getuid() == 0 or os.geteuid() == 0:
            raise Refused()
        runtime = json.loads((ROOT / "runtime.json").read_text())
        python = runtime["python"]
        report = run([python, "-I", "-S", str(ROOT / "probe/adoption_probe.py")],
                     environment=ENVIRONMENT, seconds=20)
        filtered = run([python, "-I", "-S", str(ROOT / "probe/validate_report.py")],
                       environment=ENVIRONMENT, seconds=15, input_bytes=report)
        sys.stdout.buffer.write(filtered)
        return 0
    except Exception:
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
