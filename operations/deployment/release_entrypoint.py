"""Template for two separately sealed, argument-free first-release commands.

Only the reviewed package supplies these constants. No runtime path, mode,
command, environment override or exception text is accepted as an interface.
"""
import json
import os
from pathlib import Path
import resource
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutover import Cutover, Phase, Refused as CutoverRefused
from recovery import recover_before_opening
from release_backend import Backend, Release, Refused as BackendRefused

RELEASE_PATH = None
RELEASE_SHA256 = None
OPERATION = None

SAFE_FAILURES = frozenset((
    'EXISTING_TRANSACTION_REQUIRES_RECOVERY',
    'CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED',
    'OPENING_FAILED_CURRENT_STATE_PRESERVED',
    'COHERENT_RETURN_REQUIRES_RECOVERY',
    'INTERRUPTED_STATE_NOT_AUTOMATICALLY_RESTORABLE',
    'INTERRUPTED_RETURN_HELD_FOR_RECOVERY',
    'RELEASE_HASH_REFUSED',
    'LIVE_TRANSACTION_LEASE_REFUSED',
    'CUTOVER_TIME_BUDGET_EXHAUSTED',
    'RELEASE_INTERRUPTED',
))
SUCCESS = {
    'deploy': {'schema_version': 1, 'code': 'CUTOVER_VERIFIED', 'phase': Phase.OPEN.value},
    'recover': {'schema_version': 1, 'code': 'INTERRUPTED_CUTOVER_RETURNED', 'phase': Phase.RETURNED.value},
}


class SoftStops:
    """Stop forward work once, then let its bounded safety sequence finish.

    No signal handler reads a checkpoint or performs I/O. A first TERM/INT
    becomes an ordinary Exception caught by the engines. A return, recovery,
    containment or completed transaction must not be interrupted halfway by
    another software stop; SIGKILL/power loss still use conservative recovery.
    The backend alone owns SIGALRM and its forward/return time budgets.
    """
    def __init__(self):
        self.backend = None
        self.engine = None
        self.recovery_running = False
        self.completed = False
        self.requested = False
        self.previous = {}

    def __enter__(self):
        try:
            for number in (signal.SIGTERM, signal.SIGINT):
                self.previous[number] = signal.getsignal(number)
                signal.signal(number, self.stop)
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        for number, handler in self.previous.items():
            signal.signal(number, handler)

    def stop(self, _number, _frame):
        if self.requested:
            return
        self.requested = True
        for number in self.previous:
            signal.signal(number, signal.SIG_IGN)
        if self.completed or self.recovery_running:
            return
        if self.backend is not None and (self.backend.holding is True or self.backend.recovering is True):
            return
        if self.engine is not None and self.engine.phase in (Phase.RETURNING, Phase.RETURNED):
            return
        raise BackendRefused('RELEASE_INTERRUPTED')


def main():
    backend = None
    result = {'schema_version': 1, 'code': 'FIRST_RELEASE_REFUSED', 'phase': 'unavailable'}
    succeeded = False
    try:
        if len(sys.argv) != 1 or OPERATION not in SUCCESS:
            raise BackendRefused('FIRST_RELEASE_REFUSED')
        with SoftStops() as stops:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.umask(0o077)
            release = Release.immutable_file(RELEASE_PATH, RELEASE_SHA256)
            with Backend(release) as backend:
                stops.backend = backend
                if OPERATION == 'deploy':
                    stops.engine = Cutover(backend, backend.checkpoint)
                    value = stops.engine.execute()
                else:
                    stops.recovery_running = True
                    value = recover_before_opening(backend, backend.checkpoint)
                if value != SUCCESS[OPERATION]:
                    raise BackendRefused('FIRST_RELEASE_REFUSED')
                stops.completed = True
            result = dict(SUCCESS[OPERATION])
            succeeded = True
    except BaseException as error:
        # Never serialize error text, subprocess output or a private record.
        if type(error) in (CutoverRefused, BackendRefused) and len(error.args) == 1 \
                and type(error.args[0]) is str and error.args[0] in SAFE_FAILURES:
            result['code'] = error.args[0]
        if backend is not None and backend.checkpoint is not None:
            try:
                phase = backend.checkpoint.read()
                if type(phase) is Phase:
                    result['phase'] = phase.value
            except BaseException:
                pass
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if succeeded else 1


if __name__ == '__main__':
    raise SystemExit(main())
