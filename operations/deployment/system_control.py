"""Fixed service and ingress boundary for the first deployment.

This module has no CLI. Only the sealed release backend supplies its immutable
systemctl/nft executables. It cannot read logs, accept remote unit names or run
caller-selected shell commands. New public writes stay blocked on ports80/443/
2222; administrative SSH22 and loopback remain available throughout.
"""
import os
import json
from pathlib import Path
import re
import stat
import subprocess
import time

DOMAINS = ("audition.mrj.am", "cloud.mrj.am", "forge.mrj.am", "log.mrj.am",
           "vision.mrj.am", "vise.mrj.am", "logique.echos.systems",
           "principiipetit.io", "www.principiipetit.io")
LEGACY = ("mrjam-metier", "vision", "matheval", "vise", "mrj-auth", "mrjam-courriel",
          "vision-cycle", "vision-archive", "vision-replay", "vision-closure",
          "vision-admission", "vision-purge", "vision-embeddings-backfill",
          "mrjam-admission", "mrjam-fermeture", "vision-gestion", "vision-migrate", "vision-bootstrap",
          "forgejo-identity", "forgejo-account", "forgejo-bootstrap", "keycloak",
          "mrjam-amorcage-postgresql", "mrjam-amorcage-identite", "nextcloud-setup", "vise-provision")
NEW = ("mrjam-rust-blue", "mrjam-rust-green", "mrjam-identity", "mrjam-identity-aliases", "mrjam-identity-deletion",
       "mrjam-vision-admission", "mrjam-vision-cycle", "mrjam-vision-archive",
       "mrjam-vision-replay", "mrjam-vision-closure")
ADOPTION = ("mrjam-admission-native-adopt", "mrjam-cycle-mail-adopt", "mrjam-archive-mail-adopt",
            "vision-journal-adoption", "mrjam-worker-credentials-adapt", "mrjam-kanidm-worker-provision",
            "mrjam-forgejo-probe", "mrjam-forgejo-bootstrap",
            "mrjam-adopt-matheval", "mrjam-bootstrap-journal", "mrjam-adopt-forgejo-role",
            "mrjam-upgrade-forgejo-schema",
            "mrjam-vision-admission-initialize", "mrjam-vision-cycle-initialize",
            "mrjam-vision-archive-initialize")
BACKUPS = ("forgejo-backup", "nextcloud-backup", "mrjam-sauvegarde", "mrjam-kanidm-backup",
           "postgresqlBackup-matheval", "postgresqlBackup-nextcloud",
           "forgejo-backup-qualification", "mrjam-amorcage-sauvegarde", "vise-backup")
CORE = ("nginx", "forgejo", "kanidm", "phpfpm-nextcloud", "nextcloud-cron",
        "redis-nextcloud", "vision-embeddings")
ACME = tuple("acme-renew-" + name for name in DOMAINS) + tuple("mrjam-acme-renew-" + name for name in DOMAINS)
ACME_SERVICES = ("acme-setup",) + tuple("acme-" + name for name in DOMAINS) \
    + tuple("acme-order-renew-" + name for name in DOMAINS) + ACME
SERVICES = tuple(name + ".service" for name in LEGACY + NEW + ADOPTION + BACKUPS + CORE + ACME_SERVICES)
TIMERS = tuple(name + ".timer" for name in LEGACY + NEW + BACKUPS + ("nextcloud-cron",) + ACME)
DATABASE = ("postgresql.service", "postgresql.target", "postgresql-setup.service")
ALLOWED = frozenset(SERVICES + TIMERS + DATABASE)
GATE_NAME = "mrjam_first_cutover"
MASK_DIRECTORY = Path("/run/mrjam-cutover")
GENERATOR_DIRECTORY = Path("/run/systemd/system-generators")
GENERATOR_NAME = "mrjam-first-cutover-guard"
GENERATOR = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+/bin/mrjam-first-cutover-guard\Z")
GATE_SCRIPT = b"""add table inet mrjam_first_cutover
add chain inet mrjam_first_cutover ingress { type filter hook input priority -310; policy accept; }
add rule inet mrjam_first_cutover ingress iifname != "lo" tcp dport { 80, 443, 2222 } drop
add chain inet mrjam_first_cutover egress { type filter hook output priority -310; policy accept; }
add rule inet mrjam_first_cutover egress oifname != "lo" meta skuid { 60, 71, 941, 942, 943, 944, 945, 946, 947, 948, 982, 983, 984, 990, 991, 992, 993, 995, 996, 64611 } drop
"""


class Refused(RuntimeError):
    pass


class SystemControl:
    def __init__(self, systemctl, nft, generator, run=subprocess.run, clock=time.monotonic, sleep=time.sleep,
                 mask_directory=MASK_DIRECTORY, generator_directory=GENERATOR_DIRECTORY, owner=0):
        if not isinstance(generator,str) or not GENERATOR.fullmatch(generator):
            raise Refused("GENERATOR_BINDING_REFUSED")
        self.systemctl, self.nft = str(systemctl), str(nft)
        self.generator = generator
        self.mask_directory,self.generator_directory = Path(mask_directory),Path(generator_directory)
        self.owner = owner
        self.run, self.clock, self.sleep = run, clock, sleep
        self.masked_here = set()
        self.foreign_masks = set()
        self.active_before = set()
        self.observed = False
        self.gate_created = False

    def execute(self, argv, stdin=None, capture=False, accepted=(0,), timeout=30):
        try:
            result = self.run(argv, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                              env={"LANG":"C", "LC_ALL":"C", "SYSTEMD_COLORS":"0"})
        except (OSError, subprocess.TimeoutExpired):
            raise Refused("SYSTEM_OPERATION_REFUSED") from None
        if result.returncode not in accepted:
            raise Refused("SYSTEM_OPERATION_REFUSED")
        if capture:
            if len(result.stdout) > 4096:
                raise Refused("SYSTEM_RESULT_REFUSED")
            return result.stdout.decode("ascii", "strict")
        return result.returncode

    def properties(self, unit):
        if unit not in ALLOWED:
            raise Refused("UNIT_REFUSED")
        output = self.execute([self.systemctl, "show", "--no-pager", "--property=LoadState,ActiveState,MainPID,UnitFileState", unit], capture=True)
        values = {}
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in values or key not in ("LoadState", "ActiveState", "MainPID", "UnitFileState"):
                raise Refused("SYSTEM_RESULT_REFUSED")
            values[key] = value
        if not {"LoadState", "ActiveState", "UnitFileState"}.issubset(values):
            raise Refused("SYSTEM_RESULT_REFUSED")
        if values["LoadState"] not in ("loaded", "not-found", "masked") or values["ActiveState"] not in (
                "active", "inactive", "failed", "activating", "deactivating", "reloading", "refreshing"):
            raise Refused("SYSTEM_RESULT_REFUSED")
        if unit.endswith(".service") and not values.get("MainPID", "").isdigit():
            raise Refused("SYSTEM_RESULT_REFUSED")
        return values

    def observe(self):
        if self.observed:
            raise Refused("UNIT_OBSERVATION_REPLAY_REFUSED")
        for unit in sorted(ALLOWED):
            values = self.properties(unit)
            if values["ActiveState"] in ("activating", "deactivating", "reloading", "refreshing"):
                raise Refused("CONCURRENT_SERVICE_OPERATION")
            if values["ActiveState"] == "active":
                self.active_before.add(unit)
            if values["LoadState"] == "masked" or values["UnitFileState"] in ("masked","masked-runtime"):
                if values["LoadState"] != "masked":
                    raise Refused("INEFFECTIVE_FOREIGN_MASK_REFUSED")
                self.foreign_masks.add(unit)
        # Do not take over an existing firewall boundary from another transaction.
        existing = self.execute([self.nft, "list", "table", "inet", GATE_NAME], accepted=(0, 1))
        if existing == 0:
            raise Refused("EXISTING_INGRESS_BOUNDARY_REFUSED")
        self.observed = True

    def close_ingress(self):
        if not self.observed:
            raise Refused("UNIT_OBSERVATION_REQUIRED")
        if self.gate_created:
            # Replace only our table atomically after activation, which may have
            # reloaded the host firewall. No unrelated rule is flushed.
            exists = self.execute([self.nft, "list", "table", "inet", GATE_NAME], accepted=(0, 1)) == 0
            script = (b"delete table inet mrjam_first_cutover\n" if exists else b"") + GATE_SCRIPT
        else:
            script = GATE_SCRIPT
        self.execute([self.nft, "-f", "-"], stdin=script)
        self.gate_created = True

    @staticmethod
    def sync_directory(path):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def directory(self,path,mode,create=False):
        parent=path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=self.owner or parent.st_mode & 0o022:
            raise Refused("GUARD_ANCESTOR_REFUSED")
        if create:
            try:
                path.mkdir(mode=mode)
                # The sealed backend uses umask0077; the shared generator
                # directory still needs its exact public directory mode.
                fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
                try:
                    os.fchmod(fd,mode)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.sync_directory(path.parent)
            except FileExistsError:
                pass
        item=path.lstat()
        if not stat.S_ISDIR(item.st_mode) or item.st_uid!=self.owner or stat.S_IMODE(item.st_mode)!=mode:
            raise Refused("GUARD_DIRECTORY_REFUSED")

    def install_guard(self):
        self.directory(self.generator_directory,0o755,create=True)
        target=self.generator_directory/GENERATOR_NAME
        try:
            item=target.lstat()
        except FileNotFoundError:
            os.symlink(self.generator,target)
            self.sync_directory(self.generator_directory)
        else:
            if not stat.S_ISLNK(item.st_mode) or item.st_uid!=self.owner or os.readlink(target)!=self.generator:
                raise Refused("FOREIGN_RUNTIME_GENERATOR_REFUSED")

    def publish_masks(self):
        if not self.masked_here<=ALLOWED or self.masked_here & self.foreign_masks:
            raise Refused("MASK_SET_REFUSED")
        self.directory(self.mask_directory,0o700,create=True)
        self.install_guard()
        path=self.mask_directory/"masks.json"
        try:
            item=path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(item.st_mode) or item.st_uid!=self.owner or item.st_nlink!=1 or stat.S_IMODE(item.st_mode)!=0o600:
                raise Refused("MASK_RECORD_REFUSED")
        temporary=self.mask_directory/"masks.next"
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write((json.dumps({"schema_version":1,"units":sorted(self.masked_here)},sort_keys=True)+"\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,path)
            self.sync_directory(self.mask_directory)
        finally:
            temporary.unlink(missing_ok=True)

    def verify_masks(self):
        # Runtime /run/systemd/system masks do not override NixOS /etc units.
        # Require the actual manager to see every early-generator mask.
        for unit in sorted(self.masked_here):
            if self.properties(unit)["LoadState"]!="masked":
                raise Refused("EARLY_MASK_NOT_EFFECTIVE")

    def release_masks(self, units):
        units = tuple(units)
        if any(unit not in ALLOWED for unit in units):
            raise Refused("UNIT_REFUSED")
        removed=self.masked_here & set(units)
        if removed:
            before=set(self.masked_here)
            self.masked_here-=removed
            try:
                self.publish_masks()
            except BaseException:
                self.masked_here=before
                raise
            self.execute([self.systemctl, "daemon-reload"], timeout=60)
            self.verify_masks()

    def stop(self, units):
        for unit in units:
            values = self.properties(unit)
            if values["LoadState"] != "not-found":
                self.execute([self.systemctl, "stop", "--no-block", unit])

    def wait_stopped(self, units, seconds=120):
        deadline = self.clock() + seconds
        while True:
            safe = True
            for unit in units:
                values = self.properties(unit)
                safe = safe and values["ActiveState"] in ("inactive", "failed") and int(values.get("MainPID", "0")) == 0
            if safe:
                return
            if self.clock() >= deadline:
                raise Refused("WRITERS_NOT_QUIESCENT")
            self.sleep(0.2)

    def freeze(self):
        if not self.observed:
            raise Refused("UNIT_OBSERVATION_REQUIRED")
        self.close_ingress()
        # A portable /run generator overrides the candidate's /etc generator
        # and survives activation of the old generation, which has no guard.
        # Its generator.early output overrides all normal NixOS /etc units.
        self.masked_here=set(ALLOWED)-self.foreign_masks
        self.publish_masks()
        self.execute([self.systemctl, "daemon-reload"], timeout=60)
        self.verify_masks()
        # Stop triggers before their services and all clients before PostgreSQL.
        self.stop(TIMERS)
        self.wait_stopped(TIMERS)
        backup_units = tuple(name + ".service" for name in BACKUPS)
        self.stop(backup_units)
        self.wait_stopped(backup_units)
        # Legacy backup cleanup can restart Forgejo or leave Nextcloud's
        # maintenance mode. Drain it before the final application stop.
        self.stop(tuple(unit for unit in SERVICES if unit not in backup_units))
        self.wait_stopped(SERVICES)
        self.stop(DATABASE)
        self.wait_stopped(DATABASE)
        self.verify_quiescent()

    def verify_quiescent(self):
        self.wait_stopped(tuple(sorted(ALLOWED)), seconds=5)
        if Path("/var/lib/postgresql/17/postmaster.pid").exists():
            raise Refused("POSTGRESQL_FINAL_STOP_REQUIRED")

    def start(self, units):
        self.release_masks(units)
        for unit in units:
            if unit not in ALLOWED:
                raise Refused("UNIT_REFUSED")
            self.execute([self.systemctl, "reset-failed", unit], accepted=(0, 1))
            self.execute([self.systemctl, "start", unit], timeout=180)

    def open_ingress(self):
        # The caller must durably checkpoint OPENING before invoking this.
        if not self.gate_created:
            raise Refused("INGRESS_BOUNDARY_REQUIRED")
        self.execute([self.nft, "delete", "table", "inet", GATE_NAME])
        self.gate_created = False


if __name__ == "__main__":
    raise SystemExit(64)
