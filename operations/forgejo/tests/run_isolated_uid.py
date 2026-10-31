#!/usr/bin/env python3
"""Local fixture only: isolated UID avoids the shared Cloud account's zombies.

Run in the disposable offline container, UID 59990, no host capabilities,
private output mount, immutable public inputs. Production limits are unchanged.
"""
import os
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify_nix_worker as fixture

if os.getuid() != 59990 or len(sys.argv) != 3 or sys.argv[1] not in {"qualify", "diagnose", "diagnose-http", "diagnose-frontends"}:
    raise SystemExit("ISOLATED_UID_FIXTURE_REQUIRED")
mode = sys.argv.pop(1)
limits = {name: Path('/sys/fs/cgroup', name).read_text().strip()
          for name in ('memory.max', 'pids.max', 'cpu.max')}
quota, period = map(int, limits['cpu.max'].split())
if limits['memory.max'] != str(2 * 1024**3) or limits['pids.max'] != '256' or quota != period:
    raise SystemExit('LOCAL_CGROUP_LIMITS_CHANGED')
print(json.dumps({'local_synthetic_cgroup': limits, 'uid': os.getuid()}), file=sys.stderr)
fixture.BWRAP = Path("/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0/bin/bwrap")
fixture.BWRAP_SHA256 = "cfb33892cd4f2be4328462ed5cd5bd3420459f2a177d9a61a1bc4abed07a77bc"
raise SystemExit(fixture.main(diagnostic=mode != "qualify", candidate_diagnostics=mode != "qualify",
    http_diagnostic=mode == "diagnose-http",
    frontend_diagnostic=mode == "diagnose-frontends",
    output_directory="/workspace/shared/mrjam-declarative-nix/qualifier-uid-59990"))
