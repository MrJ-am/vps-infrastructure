"""Fail-closed systemd generator for interrupted first deployment.

During a live transaction only the explicitly unmasked fixed units may run.
The runtime copy of this generator survives activation of the old generation.
Malformed metadata freezes the fixed writer set. No application row is read.
"""
import json
import os
from pathlib import Path
import stat
import sys
from cutover import Phase
from system_control import ALLOWED

CHECKPOINT = Path("/var/lib/mrjam-cutover/first-deployment/phase.json")
LIVE = Path("/run/mrjam-cutover/active.json")
MASKS = Path("/run/mrjam-cutover/masks.json")
OUTPUTS = ("/run/systemd/generator", "/run/systemd/generator.early", "/run/systemd/generator.late")


def read_private(path, owner=0, maximum=1024):
    for parent in reversed(path.parents):
        item = parent.lstat()
        if not stat.S_ISDIR(item.st_mode) or item.st_uid != owner or stat.S_IMODE(item.st_mode) & 0o022:
            raise ValueError()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as stream:
        item = os.fstat(stream.fileno())
        if not stat.S_ISREG(item.st_mode) or item.st_uid != owner or item.st_nlink != 1 or stat.S_IMODE(item.st_mode) != 0o600:
            raise ValueError()
        data = stream.read(maximum+1)
    if len(data) > maximum:
        raise ValueError()
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def active_transaction():
    try:
        value = read_private(LIVE)
        if (not isinstance(value, dict) or set(value) != {"pid", "start_ticks"}
                or type(value["pid"]) is not int or value["pid"] <= 1
                or type(value["start_ticks"]) is not str or not value["start_ticks"].isdigit()):
            return False
        proc = Path("/proc") / str(value["pid"])
        if proc.stat().st_uid != 0:
            return False
        with (proc / "stat").open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return False
        # Kernel process start ticks disambiguate PID reuse. The command name
        # and all other process metadata are neither interpreted nor emitted.
        fields = raw[raw.rfind(b")") + 2:].split()
        return len(fields) > 19 and fields[19].decode("ascii") == value["start_ticks"]
    except Exception:
        return False


def checkpoint_phase(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "phase", "elapsed_seconds"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["elapsed_seconds"]) is not int or value["elapsed_seconds"] < 0):
        raise ValueError()
    return Phase(value["phase"])


def parse_masks(value):
    if (type(value) is not dict or set(value)!={"schema_version","units"}
            or type(value["schema_version"]) is not int or value["schema_version"]!=1
            or type(value["units"]) is not list or not all(type(unit) is str for unit in value["units"])
            or value["units"]!=sorted(set(value["units"])) or not set(value["units"])<=ALLOWED):
        raise ValueError()
    return frozenset(value["units"])


def selected_masks(path=CHECKPOINT, owner=0, masks=MASKS):
    try:
        phase=checkpoint_phase(read_private(path,owner))
    except FileNotFoundError:
        # No transaction has ever begun on the host. A leftover runtime
        # record without its durable checkpoint is ambiguous and holds all.
        return ALLOWED if masks.exists() or masks.is_symlink() else frozenset()
    except Exception:
        return ALLOWED
    if phase==Phase.HELD:
        return ALLOWED
    terminal=phase in (Phase.OPEN,Phase.RETURNED)
    if not terminal and not active_transaction():
        return ALLOWED
    try:
        return parse_masks(read_private(masks,owner,maximum=65536))
    except FileNotFoundError:
        return frozenset() if terminal else ALLOWED
    except Exception:
        return ALLOWED


def must_hold(path=CHECKPOINT, owner=0):
    return bool(selected_masks(path,owner))


def generate(directory,units):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        item = os.fstat(descriptor)
        if item.st_uid != 0 or stat.S_IMODE(item.st_mode) & 0o022:
            raise RuntimeError("GENERATOR_DIRECTORY_REFUSED")
        for unit in sorted(units):
            try:
                os.symlink("/dev/null", unit, dir_fd=descriptor)
            except FileExistsError:
                # An existing symlink to /dev/null already establishes the hold.
                # Never overwrite an unrelated early-generator output.
                if os.readlink(unit, dir_fd=descriptor) != "/dev/null":
                    raise RuntimeError("GENERATOR_UNIT_CONFLICT")
    finally:
        os.close(descriptor)


def main():
    if os.geteuid() != 0 or tuple(sys.argv[1:]) != OUTPUTS:
        return 64
    units=selected_masks()
    if units:
        generate(Path(OUTPUTS[1]),units)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
