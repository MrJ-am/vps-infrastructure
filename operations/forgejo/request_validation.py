#!/usr/bin/env python3
"""Protected workflow client: one digest in, one filtered collector receipt out."""
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import time

_spec = importlib.util.spec_from_file_location("collector", Path(__file__).with_name("submit.py"))
collector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collector)
SOCKET = "/run/mrjam-validation-collector/request.sock"


def main():
    try:
        collector.require(len(sys.argv) == 1 and os.getuid() != 0, "INVALID_INVOCATION")
        proposal = os.environ.get("MRJAM_PROPOSAL_DIGEST", "")
        collector.require(re.fullmatch(r"[0-9a-f]{64}", proposal), "INVALID_PROPOSAL")
        entry = os.lstat(SOCKET)
        collector.require(stat.S_ISSOCK(entry.st_mode) and entry.st_uid == 0 and stat.S_IMODE(entry.st_mode) == 0o660, "UNTRUSTED_SOCKET")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(SOCKET)
            _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            collector.require(uid == 0, "UNTRUSTED_SOCKET")
            connection.sendall(proposal.encode("ascii") + b"\n")
            connection.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + 1850
            data = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                collector.require(remaining > 0, "COLLECTION_TIMEOUT")
                connection.settimeout(remaining)
                block = connection.recv(4097 - len(data))
                if not block:
                    break
                data.extend(block)
                collector.require(len(data) <= 4096, "RECEIPT_LIMIT")
        value = collector.parse(bytes(data))
        collector.require(type(value) is dict and set(value) == {"schema_version", "decision", "proposal_sha256", "rules_revision", "artifacts", "authority", "collection", "authenticated_validation_authority"}, "COLLECTION_REFUSED")
        collector.require(type(value["rules_revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["rules_revision"]), "INVALID_RECEIPT")
        collector.require(value["collection"] == "retained-code-artifacts" and value["authenticated_validation_authority"] is False, "INVALID_RECEIPT")
        receipt = {key: content for key, content in value.items() if key not in ("collection", "authenticated_validation_authority")}
        collector.validate_receipt(receipt, proposal, value["rules_revision"])
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except collector.Refused as error:
        print(json.dumps({"decision": "reject", "code": str(error)}, separators=(",", ":")))
        return 2
    except Exception:
        print('{"decision":"reject","code":"COLLECTION_FAILED"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
