"""First-cutover transaction; no CLI command, SQL, path or environment input.

The final release supplies a sealed backend with exact generation and helper
paths. This engine alone cannot activate anything. Its checkpoints are durable
before the corresponding irreversible boundary, especially public reopening.
"""
from enum import StrEnum
import json
import os
from pathlib import Path
import stat
import time


class Phase(StrEnum):
    PREPARED = "prepared"
    FREEZING = "freezing"
    FROZEN = "frozen"
    SNAPSHOT = "snapshot-complete"
    CANDIDATE = "candidate-installed"
    ADOPTED = "state-adopted"
    VERIFIED = "private-verification-complete"
    OPENING = "opening-public-writes"
    OPEN = "public-writes-open"
    RETURNING = "returning-before-public-writes"
    RETURNED = "previous-generation-restored"
    HELD = "held-for-recovery"


class Refused(RuntimeError):
    """Only a closed error code may leave this module."""


class Checkpoint:
    """Root-private durable metadata, separate from the private snapshot."""
    def __init__(self, directory, uid=0):
        self.directory = Path(directory)
        metadata = self.directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise Refused("CHECKPOINT_DIRECTORY_REFUSED")
        self.path = self.directory / "phase.json"
        self.owner = uid

    def write(self, phase, elapsed):
        # No application values, arbitrary diagnostics, paths or subprocess output.
        document = {"schema_version": 1, "phase": Phase(phase).value,
                    "elapsed_seconds": max(0, int(elapsed))}
        temporary = self.directory / "phase.next"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write((json.dumps(document, sort_keys=True) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            folder = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self):
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != self.owner or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
                raise Refused("CHECKPOINT_FILE_REFUSED")
            data = stream.read(1025)
        if len(data) > 1024:
            raise Refused("CHECKPOINT_FILE_REFUSED")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise Refused("CHECKPOINT_FILE_REFUSED")
                result[key] = value
            return result
        value = json.loads(data, object_pairs_hook=pairs)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "phase", "elapsed_seconds"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or type(value["elapsed_seconds"]) is not int or value["elapsed_seconds"] < 0):
            raise Refused("CHECKPOINT_FILE_REFUSED")
        return Phase(value["phase"])


class Cutover:
    """Fixed sequence over a sealed local backend, never remote run(command)."""
    # Initial interruption allowance is three hours. Stop forward progress after
    # 90 minutes, leaving the other 90 for the qualified coherent return.
    FORWARD_LIMIT = 90 * 60
    TOTAL_LIMIT = 3 * 60 * 60

    def __init__(self, backend, checkpoint, clock=time.monotonic):
        self.backend = backend
        self.checkpoint = checkpoint
        self.clock = clock
        self.started = None
        self.phase = Phase.PREPARED
        self.snapshot_complete = False
        self.reopening_started = False

    def transition(self, phase):
        elapsed = self.clock() - self.started if self.started is not None else 0
        self.checkpoint.write(phase, elapsed)
        self.phase = phase

    def forward_budget(self):
        if self.clock() - self.started >= self.FORWARD_LIMIT:
            raise Refused("RETURN_MARGIN_REQUIRED")

    def execute(self):
        try:
            self.checkpoint.read()
        except FileNotFoundError:
            pass
        else:
            raise Refused("EXISTING_TRANSACTION_REQUIRES_RECOVERY")
        # Includes immutable release/provenance, generation, reserved identities,
        # capacity and snapshot-destination checks. No service stopped on failure.
        self.backend.preflight()
        self.transition(Phase.PREPARED)
        self.started = self.clock()
        try:
            self.transition(Phase.FREEZING)
            self.backend.freeze()
            self.backend.verify_quiescent()
            self.transition(Phase.FROZEN)
            self.forward_budget()
            self.backend.snapshot()
            self.backend.verify_snapshot()
            self.snapshot_complete = True
            self.transition(Phase.SNAPSHOT)
            self.forward_budget()
            self.backend.install_candidate()
            self.transition(Phase.CANDIDATE)
            self.forward_budget()
            self.backend.adopt_private_state()
            self.transition(Phase.ADOPTED)
            self.forward_budget()
            self.backend.start_private_services()
            self.backend.verify_private_services()
            self.transition(Phase.VERIFIED)
            self.forward_budget()
            # Persist refusal of rollback BEFORE any frontend, writer timer,
            # mail sender or other new writer can be exposed. An ambiguous
            # partial opening must never restore an older application snapshot.
            self.reopening_started = True
            self.transition(Phase.OPENING)
            self.backend.open_public_writes()
            self.transition(Phase.OPEN)
            self.backend.verify_public_services()
            return {"schema_version": 1, "code": "CUTOVER_VERIFIED", "phase": self.phase.value}
        except Exception:
            if self.reopening_started:
                # Keep the current state. The backend only closes ingress and
                # scheduled writes; it must not restore or delete application data.
                self.backend.hold_current_state()
                self.transition(Phase.HELD)
                raise Refused("OPENING_FAILED_CURRENT_STATE_PRESERVED") from None
            self.return_before_opening()
            raise Refused("CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED") from None

    def return_before_opening(self):
        durable_phase = self.checkpoint.read()
        if self.reopening_started or self.phase in (Phase.OPENING, Phase.OPEN, Phase.HELD, Phase.RETURNED) \
                or durable_phase in (Phase.OPENING, Phase.OPEN, Phase.HELD, Phase.RETURNED):
            raise Refused("RESTORE_AFTER_PUBLIC_WRITES_REFUSED")
        if self.started is None or durable_phase != self.phase:
            raise Refused("INTERRUPTED_TRANSACTION_REQUIRES_RECOVERY")
        try:
            self.transition(Phase.RETURNING)
            self.backend.freeze()
            self.backend.verify_quiescent()
            if self.snapshot_complete:
                self.backend.verify_snapshot()
                # Quarantine candidate files, retain them privately, then restore
                # the matching offline cluster and application files together.
                self.backend.restore_snapshot()
            self.backend.restore_previous_generation()
            self.backend.verify_previous_private_services()
            # Keep staged as the default boot until old state and services
            # have been verified. Once the old boot can accept new writes,
            # another snapshot restore must already be forbidden durably.
            self.transition(Phase.RETURNED)
            self.backend.reopen_previous_services()
        except Exception:
            self.backend.hold_current_state()
            self.transition(Phase.HELD)
            raise Refused("COHERENT_RETURN_REQUIRES_RECOVERY") from None


if __name__ == "__main__":
    # Production entrypoint comes only from a complete, separately qualified
    # release package. This preparation module has no executable backend.
    raise SystemExit(64)
