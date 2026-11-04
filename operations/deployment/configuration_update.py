"""State machine for one sealed, configuration-only update.

No CLI, filesystem, network, SQL or caller-selected commands. The reviewed
adapter must hold the common deployment lock and supply durable checkpoints.
Only byte-qualified updates with unchanged application units are admissible.
This administrative mechanism is not an ordinary CI deployment authority.
"""


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


PHASES = frozenset(("prepared", "activating", "live-verified", "boot-selecting",
                    "complete", "returning", "returned"))


def update(adapter):
    """Adapter binds two immutable generations and has no candidate inputs.

    observe() returns symbolic generation identities only. All generation
    operations and health checks are fixed by the adapter, not checkpoint
    fields. Crash recovery never restores application data.
    """
    adapter.preflight()
    state = adapter.read_checkpoint()
    require(state is None or state in PHASES, "CHECKPOINT_REFUSED")
    pair = adapter.observe()
    require(type(pair) is tuple and len(pair) == 2
            and all(value in ("previous", "candidate") for value in pair),
            "FOREIGN_GENERATION_REFUSED")
    if state == "complete":
        require(pair == ("candidate", "candidate"), "COMPLETED_STATE_CHANGED")
        adapter.verify_candidate()
        return "CONFIGURATION_ALREADY_VERIFIED"
    if state == "returned":
        require(pair == ("previous", "previous"), "RETURNED_STATE_CHANGED")
        adapter.verify_previous()
        return "CONFIGURATION_ALREADY_RETURNED"
    if state is None:
        require(pair == ("previous", "previous"), "INITIAL_STATE_REFUSED")
        adapter.checkpoint("prepared")
    elif state != "prepared":
        # A process which disappeared during a switch cannot infer its outcome
        # from a checkpoint. Return both pointers to the qualified predecessor.
        return restore(adapter)
    else:
        require(pair == ("previous", "previous"), "PREPARED_STATE_CHANGED")
    try:
        adapter.checkpoint("activating")
        adapter.activate_candidate()
        require(adapter.observe() == ("candidate", "previous"), "LIVE_STATE_REFUSED")
        adapter.verify_candidate()
        adapter.checkpoint("live-verified")
        adapter.checkpoint("boot-selecting")
        adapter.select_candidate_boot()
        require(adapter.observe() == ("candidate", "candidate"), "BOOT_STATE_REFUSED")
        adapter.verify_candidate()
        adapter.checkpoint("complete")
        return "CONFIGURATION_VERIFIED"
    except Exception:
        return restore(adapter)


def restore(adapter):
    pair = adapter.observe()
    require(type(pair) is tuple and len(pair) == 2
            and all(value in ("previous", "candidate") for value in pair),
            "FOREIGN_GENERATION_REFUSED")
    adapter.checkpoint("returning")
    adapter.activate_previous()
    adapter.select_previous_boot()
    require(adapter.observe() == ("previous", "previous"), "RETURN_STATE_REFUSED")
    adapter.verify_previous()
    adapter.checkpoint("returned")
    return "CONFIGURATION_RETURNED"
