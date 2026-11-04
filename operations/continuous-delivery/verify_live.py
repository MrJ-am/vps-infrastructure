#!/usr/bin/env python3
"""Measure one live binary rollback, then let main deliver the healthy candidate again.

Administrator-only operational test. It briefly pauses the new serving process;
it never reads application data or changes a database.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    if os.getuid() != 0 or len(sys.argv) != 3 or not re.fullmatch(r"[0-9a-f]{40}", sys.argv[2]):
        raise ValueError("Usage: verify_live.py INSTALLED_PACKAGE EXACT_MAIN_COMMIT")
    sys.path.insert(0, str(Path(sys.argv[1], "operations/continuous-delivery")))
    import deploy
    current_file = deploy.STATE / "current.json"
    state = json.loads(current_file.read_text())
    revision = sys.argv[2]
    if state["revision"] != revision or state["slot"] not in deploy.PORTS:
        raise RuntimeError("Expected the just-delivered main revision")
    old, new = state["previous_slot"], state["slot"]
    if not deploy.probe(old) or not deploy.probe(new):
        raise RuntimeError("Both versions must be ready before this test")
    unit = "mrjam-rust-" + new + ".service"
    started = time.monotonic()
    automatic = False
    try:
        deploy.command(["systemctl", "kill", "--kill-whom=main", "--signal=SIGSTOP", unit])
        while time.monotonic() - started < 5:
            if deploy.active_slot(deploy.NGINX_CONF.read_text()) == old and deploy.probe(old):
                try:
                    # The paused candidate cannot answer: a successful request
                    # through real Nginx proves the old version is serving again.
                    status = deploy.command(["curl", "--silent", "--fail", "--max-time", "0.5",
                                             "--resolve", "vision.mrj.am:443:127.0.0.1",
                                             "--output", "/dev/null", "--write-out", "%{http_code}",
                                             "https://vision.mrj.am/"], timeout=1)
                    if status == "200":
                        automatic = True
                        break
                except (subprocess.SubprocessError, OSError):
                    pass
            time.sleep(0.05)
        elapsed = time.monotonic() - started
        if not automatic:
            deploy.rollback({"revision": revision,
                             "old_configuration": state["previous_configuration"],
                             "old_state": state["previous_state"]})
    finally:
        subprocess.run(["systemctl", "kill", "--kill-whom=main", "--signal=SIGCONT", unit],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not automatic:
        raise RuntimeError("Automatic return exceeded five seconds; previous routing restored")
    deadline = time.monotonic() + 10
    while not deploy.probe(new):
        if time.monotonic() >= deadline:
            raise RuntimeError("Candidate did not resume; previous routing retained")
        time.sleep(0.1)
    failure = deploy.STATE / "failed.json"
    if failure.exists() and json.loads(failure.read_text())["revision"] == revision:
        failure.unlink()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if current_file.exists():
            final = json.loads(current_file.read_text())
            if final["revision"] == revision and deploy.probe(final["slot"]):
                deploy.public_check()
                proof = {"revision": revision, "automatic_rollback": True,
                         "failure_detection_and_rollback_seconds": round(elapsed, 3),
                         "first_cutover_seconds": state["cutover_seconds"],
                         "final_cutover_seconds": final["cutover_seconds"],
                         "active_slot": final["slot"], "previous_slot_ready": deploy.probe(final["previous_slot"])}
                deploy.atomic_json(deploy.STATE / "verification.json", proof)
                print(json.dumps(proof))
                return
        time.sleep(0.2)
    raise RuntimeError("Previous version serves traffic; healthy candidate was not delivered again")


if __name__ == "__main__":
    main()
