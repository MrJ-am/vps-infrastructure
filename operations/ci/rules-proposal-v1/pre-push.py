"""Sealed Git pre-push: create one exact ref, never advance an existing ref."""
import hashlib
import json
from pathlib import Path
import sys

BINDING = "@BINDING@"
BINDING_SHA256 = "@BINDING_SHA256@"
URL = "http://127.0.0.1:3004/MrJ-am/mrjam-validation.git"


def validate(arguments, raw, binding):
    if arguments != [URL, URL] or type(raw) is not bytes or len(raw) > 4096:
        return False
    head = binding["head"]
    ref = "refs/heads/bootstrap-ci-workflow-" + head[:16]
    return raw == (head+" "+head+" "+ref+" "+"0"*40+"\n").encode("ascii")


def main():
    try:
        raw = Path(BINDING).read_bytes()
        if hashlib.sha256(raw).hexdigest() != BINDING_SHA256:
            return 1
        return 0 if validate(sys.argv[1:], sys.stdin.buffer.read(4097), json.loads(raw)) else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
