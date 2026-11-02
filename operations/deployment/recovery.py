"""Fixed coherent return for an interrupted, pre-opening first deployment.

This is an internal engine, with no CLI. A sealed backend first validates the
release binding and the private record of previously active units, reacquires
the single-host lock and live lease, and establishes the network boundary.
Recovery never resumes forward migration or accepts a new target generation.
"""
import time
from cutover import Phase, Refused

PRE_SNAPSHOT = frozenset((Phase.PREPARED, Phase.FREEZING, Phase.FROZEN))
RESTORABLE = frozenset((Phase.SNAPSHOT, Phase.CANDIDATE, Phase.ADOPTED,
                       Phase.VERIFIED, Phase.RETURNING))


def recover_before_opening(backend, checkpoint, clock=time.monotonic):
    initial = checkpoint.read()
    # HELD intentionally remains conservative: it can result from a failed
    # return OR an uncertain public opening. A generic retry must not erase
    # potentially accepted writes. OPEN and RETURNED need no recovery here.
    if initial not in PRE_SNAPSHOT | RESTORABLE:
        raise Refused("INTERRUPTED_STATE_NOT_AUTOMATICALLY_RESTORABLE")
    backend.preflight_recovery()
    started = clock()

    def transition(phase):
        checkpoint.write(phase, clock() - started)

    try:
        backend.freeze()
        backend.verify_quiescent()
        if initial in RESTORABLE:
            # RETURNING is only retried with a complete verified offline
            # snapshot. Partial creation never authorises an extraction.
            backend.verify_snapshot()
        else:
            # Before the durable snapshot checkpoint the backend must prove
            # adoption was never entered, even if boot already selects staged.
            backend.verify_adoption_not_started()
        transition(Phase.RETURNING)
        if initial in RESTORABLE:
            backend.restore_snapshot()
        backend.restore_previous_generation()
        backend.verify_previous_private_services()
        transition(Phase.RETURNED)
        backend.reopen_previous_services()
        return {"schema_version": 1, "code": "INTERRUPTED_CUTOVER_RETURNED",
                "phase": Phase.RETURNED.value}
    except Exception:
        try:
            backend.hold_current_state()
        finally:
            transition(Phase.HELD)
        raise Refused("INTERRUPTED_RETURN_HELD_FOR_RECOVERY") from None


if __name__ == "__main__":
    raise SystemExit(64)
