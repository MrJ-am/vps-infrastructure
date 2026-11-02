"""Fixed administrative correction007 -> unicast001; no arguments or SQL."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
import tempfile

import configuration_update as C
from generation import Generations

PREVIOUS = "/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git"
CANDIDATE = "/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git"
STAGED = "/nix/store/hbfh9zzrv35kxck3p56yv7pxxw22fb3y-nixos-system-srv1982677-26.05pre-git"
SYSTEMD = "/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/"
NIX = "/nix/store/i4bv0lvk0gfzllcy2kqgz3iam0aw4c4i-nix-2.34.8/bin/"
STATE = Path("/var/lib/mrjam-cutover/resolver-update-001")
LOCK = Path("/var/lib/mrjam-cutover/first-deployment/transaction.lock")
SERVICES = ("nginx", "forgejo", "kanidm", "postgresql", "mrjam-rust-blue",
            "mrjam-identity", "mrjam-identity-deletion", "mrjam-vision-admission",
            "mrjam-vision-closure", "systemd-resolved", "sshd")
CONFIG_HASH = {
    PREVIOUS: "b8985c71edbb05c839d1a2cbed87b7561d4af36170201ef959a17ef08af6ee8b",
    CANDIDATE: "99b78f07d835746413e9ab4d044fe262fac63c4c58c938f05d6edf0028976636",
}


def run(arguments, timeout=30):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                            env={"LANG": "C", "LC_ALL": "C", "NIX_PATH": ""})
    C.require(result.returncode == 0, "FIXED_OPERATION_REFUSED")


def directory(path):
    info = path.lstat()
    C.require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
              and stat.S_IMODE(info.st_mode) == 0o700, "STATE_DIRECTORY_REFUSED")


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


class Adapter:
    def __init__(self):
        self.generations = Generations(PREVIOUS, STAGED, CANDIDATE, NIX + "nix-env")

    def preflight(self):
        C.require(os.geteuid() == 0, "ROOT_REQUIRED")
        self.generations.verify_paths()
        for path in (PREVIOUS, CANDIDATE):
            run([NIX + "nix-store", "--verify-path", path], 60)
            raw = (Path(path) / "etc/systemd/resolved.conf").read_bytes()
            C.require(hashlib.sha256(raw).hexdigest() == CONFIG_HASH[path], "CONFIGURATION_CHANGED")
        directory(STATE.parent)
        if not STATE.exists():
            STATE.mkdir(mode=0o700)
            sync(STATE.parent)
        directory(STATE)

    def observe(self):
        names = {PREVIOUS: "previous", CANDIDATE: "candidate"}
        return tuple(names.get(os.path.realpath(path), "foreign")
                     for path in ("/run/current-system", "/nix/var/nix/profiles/system"))

    def read_checkpoint(self):
        path = STATE / "checkpoint.json"
        try: fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError: return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            C.require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                      and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600
                      and 0 < info.st_size <= 1024, "CHECKPOINT_METADATA_REFUSED")
            raw = stream.read(1025)
        value = json.loads(raw)
        C.require(type(value) is dict and set(value) == {"previous", "candidate", "phase"}
                  and value["previous"] == PREVIOUS and value["candidate"] == CANDIDATE,
                  "CHECKPOINT_BINDING_REFUSED")
        C.require(type(value["phase"]) is str and value["phase"] in C.PHASES,
                  "CHECKPOINT_PHASE_REFUSED")
        return value["phase"]

    def checkpoint(self, phase):
        C.require(phase in C.PHASES, "CHECKPOINT_PHASE_REFUSED")
        raw = json.dumps({"previous": PREVIOUS, "candidate": CANDIDATE, "phase": phase},
                         sort_keys=True, separators=(",", ":")).encode()
        # Keep an incomplete earlier temporary as evidence without preventing
        # the durable return checkpoint after an interrupted write.
        fd, temporary = tempfile.mkstemp(prefix="checkpoint-", suffix=".next", dir=STATE)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, STATE / "checkpoint.json")
        sync(STATE)

    def verify(self, generation):
        raw = Path("/etc/systemd/resolved.conf").read_bytes()
        C.require(hashlib.sha256(raw).hexdigest() == CONFIG_HASH[generation], "LIVE_CONFIG_REFUSED")
        # is-active with several units succeeds when any one is active.
        for service in SERVICES:
            run([SYSTEMD + "systemctl", "is-active", "--quiet", service + ".service"])
        # Use the real retained DNS service, suppressing response contents.
        run([SYSTEMD + "resolvectl", "query", "--cache=no", "log.mrj.am"], 20)
        if generation == CANDIDATE:
            for path in ("/proc/net/tcp", "/proc/net/tcp6", "/proc/net/udp", "/proc/net/udp6"):
                with open(path, "rb") as stream: raw = stream.read(262145)
                C.require(len(raw) <= 262144, "PORT_OBSERVATION_LIMIT")
                lines = raw.decode("ascii").splitlines()
                C.require(lines and len(lines) <= 2049, "PORT_OBSERVATION_LIMIT")
                for row in lines[1:]:
                    fields = row.split()
                    C.require(len(fields) >= 4, "PORT_OBSERVATION_REFUSED")
                    C.require(int(fields[1].rsplit(":", 1)[1], 16) != 5355,
                              "LLMNR_STILL_BOUND")

    def verify_candidate(self): self.verify(CANDIDATE)
    def verify_previous(self): self.verify(PREVIOUS)
    def activate_candidate(self): self.generations.activate(CANDIDATE)
    def select_candidate_boot(self): self.generations.select_boot(CANDIDATE)
    def activate_previous(self): self.generations.activate(PREVIOUS)
    def select_previous_boot(self): self.generations.select_boot(PREVIOUS)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0: return 64
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    lock = None
    try:
        directory(LOCK.parent.parent)
        directory(LOCK.parent)
        lock = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        info = os.fstat(lock)
        C.require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                  and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
                  "TRANSACTION_LOCK_REFUSED")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = C.update(Adapter())
    except Exception:
        code = "CONFIGURATION_UPDATE_REFUSED"
    finally:
        if lock is not None: os.close(lock)
    print(json.dumps({"schema_version": 1, "code": code, "application_data_restored": False},
                     sort_keys=True, separators=(",", ":")))
    return 0 if code in ("CONFIGURATION_VERIFIED", "CONFIGURATION_ALREADY_VERIFIED") else 1


if __name__ == "__main__": raise SystemExit(main())
