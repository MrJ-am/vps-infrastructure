"""Sealed first-cutover backend. This module has deliberately NO executable CLI.

A separately reviewed entrypoint must bind the immutable release file and its
SHA-256, acquire this backend as a context manager, then select Cutover.execute
or the separate conservative recovery engine. No caller can supply commands,
SQL, service names, URLs, paths, generations or environment overrides at runtime.
All subprocess diagnostics stay private; only closed engine codes may leave.
"""
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import resource
import shutil
import signal
import stat
import subprocess
import time
from types import MappingProxyType

from cutover import Checkpoint, Phase
from generation import Generations, STORE
from snapshot import FrozenSnapshot, ROOTS, REQUIRED
from system_control import SystemControl, ALLOWED, DATABASE, BACKUPS, TIMERS, ACME_SERVICES, GATE_NAME, GENERATOR, GENERATOR_DIRECTORY, GENERATOR_NAME
import stage_adoption
import stage_credentials

PREVIOUS = "/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
STATE = Path("/var/lib/mrjam-cutover/first-deployment")
VOLATILE = Path("/run/mrjam-cutover")
HOST = "srv1982677"
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAR = re.compile(r"sha256-[A-Za-z0-9+/]{43}=\Z")
TOOLS = {"systemctl":"/bin/systemctl", "nft":"/bin/nft", "nix":"/bin/nix",
         "nix_store":"/bin/nix-store", "nix_env":"/bin/nix-env",
         "python":"/bin/python3", "curl":"/bin/curl", "tar":"/bin/tar"}
HELPERS = {"capabilities":"/libexec/probe-standalone.py",
           "obligations":"/libexec/preflight_obligations.py",
           "forgejo_sso":"/libexec/forgejo_sso_probe.py",
           "forgejo_probe":"/bin/mrjam-forgejo-probe",
           "forgejo_cleanup":"/bin/mrjam-forgejo-cleanup",
           "forgejo_sources":"/bin/mrjam-first-release-sources-probe",
           "forgejo_governance":"/bin/mrjam-first-release-governance"}
DOMAINS = ("audition.mrj.am", "cloud.mrj.am", "forge.mrj.am", "log.mrj.am",
           "logique.echos.systems", "principiipetit.io", "vision.mrj.am", "www.principiipetit.io")
READY_CAPABILITIES = ("static-assets", "mateval-collection", "mateval-administration",
                      "vision-http", "vision-mcp", "vision-administration",
                      "audition-http", "audition-mcp", "log-presentation")
FILE_ADOPTIONS = ("mrjam-worker-credentials-adapt.service", "mrjam-admission-native-adopt.service",
                  "mrjam-cycle-mail-adopt.service", "mrjam-archive-mail-adopt.service")
SQL_ADOPTIONS = ("mrjam-adopt-matheval.service", "mrjam-bootstrap-journal.service",
                 "mrjam-upgrade-forgejo-schema.service", "mrjam-adopt-forgejo-role.service")
PRIVATE_SERVICES = ("kanidm.service", "mrjam-identity.service", "mrjam-identity-aliases.service",
                    "mrjam-identity-deletion.service", "vision-embeddings.service",
                    "redis-nextcloud.service", "nextcloud-setup.service", "phpfpm-nextcloud.service",
                    "forgejo.service", "mrjam-vision-admission.service", "mrjam-vision-closure.service",
                    "mrjam-rust-blue.service", "nginx.service")
PUBLIC_TIMERS = ("mrjam-identity-aliases.timer", "mrjam-vision-cycle.timer", "mrjam-vision-archive.timer",
                 "mrjam-vision-replay.timer", "nextcloud-cron.timer", "mrjam-sauvegarde.timer",
                 "forgejo-backup.timer", "nextcloud-backup.timer", "postgresqlBackup-matheval.timer",
                 "postgresqlBackup-nextcloud.timer") + tuple("mrjam-acme-renew-"+name+".timer" for name in DOMAINS)
TIMER_SERVICES = tuple(name.removesuffix(".timer")+".service" for name in PUBLIC_TIMERS)
RETURN_DELAYED = frozenset(TIMERS) | frozenset(name+".service" for name in BACKUPS+ACME_SERVICES+(
    "mrjam-courriel", "vision-cycle", "vision-archive", "vision-replay", "vision-purge",
    "vision-embeddings-backfill", "mrjam-vision-cycle", "mrjam-vision-archive", "mrjam-vision-replay",
    "mrjam-identity-aliases", "nextcloud-cron"))
# Previous NixOS ACME timers name their target explicitly; it is not the
# default timer stem. Other units in this closed inventory use the default.
RETURN_TIMER_SERVICES = {timer:timer.removesuffix(".timer")+".service" for timer in TIMERS}
RETURN_TIMER_SERVICES.update({"acme-renew-"+domain+".timer":"acme-order-renew-"+domain+".service"
                             for domain in DOMAINS+("vise.mrj.am",)})
RETURN_TRIGGERED_ONLY = frozenset(name+".service" for name in BACKUPS+ACME_SERVICES)
RETURN_OPTIONAL = frozenset(("vise.service", "vise.timer", "vise-provision.service", "vise-provision.timer",
    "vise-backup.service", "vise-backup.timer", "acme-vise.mrj.am.service",
    "acme-order-renew-vise.mrj.am.service", "acme-renew-vise.mrj.am.service", "acme-renew-vise.mrj.am.timer",
    "mrjam-acme-renew-vise.mrj.am.service", "mrjam-acme-renew-vise.mrj.am.timer"))
LEGACY_JOURNALS = ("effacements/demandes.jsonl", "cycle/effacements.jsonl", "fermeture/effacements.jsonl")
RETAINED_IDENTITIES = {"postgres":(71,71), "forgejo":(982,982), "kanidm":(983,983),
                       "nextcloud":(990,990), "nginx":(60,60), "acme":(996,995), "mrjam-metier":(984,984)}
REQUIRED_PRIVATE = ("kanidm-admission.token", "kanidm-cycle.token", "kanidm-replay.token",
                    "kanidm-vision.secret", "proton-smtp.json", "cycle.json", "fermeture-hook.secret")
SOURCE_REPOSITORIES = ("Signature", "apprendre-a-demontrer", "etp-vie-affective", "matheval", "mrjam-plateforme",
                       "mrjam-validation", "style-mrjam", "vision", "vps-infrastructure")
STAGING_DIRECTORIES = (stage_credentials.OUTPUT,) + tuple(Path("/run")/name for name in sorted(stage_adoption.PROFILES))


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def strict_json(raw, maximum=1048576):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "DOCUMENT_SIZE_REFUSED")
    def pairs(items):
        result = {}
        for key,value in items:
            require(key not in result, "DOCUMENT_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused("DOCUMENT_NUMBER_REFUSED")))
    except (UnicodeError, ValueError, RecursionError):
        raise Refused("DOCUMENT_FORMAT_REFUSED") from None


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path, create=False, owner=0):
    path = Path(path)
    require(path.is_absolute(), "PRIVATE_PATH_REFUSED")
    for parent in reversed(path.parents):
        item = parent.lstat()
        require(stat.S_ISDIR(item.st_mode) and item.st_uid == owner and not item.st_mode & 0o022,
                "PRIVATE_ANCESTOR_REFUSED")
    if create:
        try:
            path.mkdir(mode=0o700)
            sync_directory(path.parent)
        except FileExistsError:
            pass
    item = path.lstat()
    require(stat.S_ISDIR(item.st_mode) and item.st_uid == owner
            and stat.S_IMODE(item.st_mode) == 0o700, "PRIVATE_DIRECTORY_REFUSED")


def private_read(path, maximum=65536, owner=0, links=(1,)):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        item = os.fstat(stream.fileno())
        require(stat.S_ISREG(item.st_mode) and item.st_uid == owner and item.st_gid == 0
                and item.st_nlink in links and stat.S_IMODE(item.st_mode) == 0o600,
                "PRIVATE_FILE_REFUSED")
        raw = stream.read(maximum+1)
    return strict_json(raw, maximum)


def publish_private(path, value, replace=False):
    path = Path(path)
    raw = (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
    require(len(raw) <= 65536, "PRIVATE_METADATA_SIZE_REFUSED")
    pending = path.with_name(path.name+".next")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            item = path.lstat()
            require(stat.S_ISREG(item.st_mode) and item.st_uid == 0 and item.st_nlink == 1
                    and stat.S_IMODE(item.st_mode) == 0o600, "PRIVATE_METADATA_REPLACEMENT_REFUSED")
            os.replace(pending,path)
        else:
            os.link(pending,path,follow_symlinks=False)
            pending.unlink()
        sync_directory(path.parent)
    finally:
        pending.unlink(missing_ok=True)


class Release:
    """Read only a hash-bound immutable manifest from the reviewed entrypoint."""
    def __init__(self, raw, expected_hash):
        require(type(raw) is bytes and type(expected_hash) is str and HEX.fullmatch(expected_hash)
                and hashlib.sha256(raw).hexdigest() == expected_hash, "RELEASE_HASH_REFUSED")
        value = strict_json(raw,4*1024*1024)
        require(type(value) is dict and set(value) == {
            "schema_version","target","generations","tools","helpers","ca_file","artifacts","forgejo_binding_sha256","generator"},
            "RELEASE_FIELDS_REFUSED")
        require(type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["target"] == HOST, "RELEASE_TARGET_REFUSED")
        generations = value["generations"]
        require(type(generations) is dict and set(generations) == {"previous","staged","promoted"}
                and generations["previous"] == PREVIOUS
                and all(type(v) is str and STORE.fullmatch(v) for v in generations.values())
                and len(set(generations.values())) == 3,
                "RELEASE_GENERATIONS_REFUSED")
        selected = set(generations.values())
        require(type(value["generator"]) is str and GENERATOR.fullmatch(value["generator"]),"RELEASE_GENERATOR_REFUSED")
        selected.add(value["generator"].removesuffix("/bin/mrjam-first-cutover-guard"))
        for name, suffixes in (("tools",TOOLS),("helpers",HELPERS)):
            entries = value[name]
            require(type(entries) is dict and set(entries) == set(suffixes), "RELEASE_PROGRAMS_REFUSED")
            for key,suffix in suffixes.items():
                path = entries[key]
                require(type(path) is str and path.endswith(suffix)
                        and STORE.fullmatch(path.removesuffix(suffix)), "RELEASE_PROGRAM_REFUSED")
                selected.add(path.removesuffix(suffix))
        ca = value["ca_file"]
        require(type(ca) is str and ca.endswith("/ca.pem") and STORE.fullmatch(ca.removesuffix("/ca.pem")),
                "RELEASE_CA_REFUSED")
        selected.add(ca.removesuffix("/ca.pem"))
        artifacts = value["artifacts"]
        require(type(artifacts) is dict and 1 <= len(artifacts) <= 4096 and selected <= set(artifacts),
                "RELEASE_ARTIFACT_SET_REFUSED")
        require(all(type(path) is str and STORE.fullmatch(path) and type(digest) is str and NAR.fullmatch(digest)
                    for path,digest in artifacts.items()), "RELEASE_ARTIFACT_REFUSED")
        require(type(value["forgejo_binding_sha256"]) is str and HEX.fullmatch(value["forgejo_binding_sha256"]),
                "RELEASE_FORGEJO_BINDING_REFUSED")
        self.digest = expected_hash
        self.generations = MappingProxyType(generations)
        self.tools = MappingProxyType(value["tools"])
        self.helpers = MappingProxyType(value["helpers"])
        self.artifacts = MappingProxyType(artifacts)
        self.roots = frozenset(selected)
        self.forgejo_binding = value["forgejo_binding_sha256"]
        self.generator = value["generator"]
        self.ca_file = ca

    @classmethod
    def immutable_file(cls,path,expected_hash):
        path = Path(path)
        require(len(path.parts) == 5 and path.parts[1:3] == ("nix","store")
                and STORE.fullmatch(str(path.parent)), "RELEASE_LOCATION_REFUSED")
        fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        with os.fdopen(fd,"rb") as stream:
            item = os.fstat(stream.fileno())
            require(stat.S_ISREG(item.st_mode) and item.st_uid == 0 and not item.st_mode & 0o222,
                    "RELEASE_IMMUTABILITY_REFUSED")
            raw = stream.read(4*1024*1024+1)
        return cls(raw,expected_hash)


class DeadlineSnapshot(FrozenSnapshot):
    def __init__(self,backend):
        super().__init__("/var/lib",STATE/"snapshot",backend.release.tools["tar"])
        self.backend = backend

    def command(self,args,timeout):
        self.backend.command([self.tar,*args],timeout=timeout)


class Backend:
    """No production constructor is exposed until its entrypoint is qualified."""
    def __init__(self,release,run=subprocess.run,clock=time.monotonic,sleep=time.sleep):
        require(isinstance(release,Release),"SEALED_RELEASE_REQUIRED")
        self.release,self.run,self.clock,self.sleep = release,run,clock,sleep
        self.control = SystemControl(release.tools["systemctl"],release.tools["nft"],release.generator,run=self.timed_run,clock=clock)
        self.generations = Generations(**dict(release.generations),nix_env=release.tools["nix_env"],run=self.timed_run)
        self.checkpoint = None
        self.saved = None
        self.lock = None
        self.started = None
        self.original = None
        self.boot_selected = False
        self.recovering = False
        self.holding = False
        self.signal_before = None
        self.source_archive_bytes = 0

    def __enter__(self):
        require(os.geteuid() == 0, "ROOT_IDENTITY_REQUIRED")
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        os.umask(0o077)
        private_directory(STATE.parent,True)
        private_directory(STATE,True)
        private_directory(VOLATILE,True)
        self.lock = os.open(STATE/"transaction.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            item = os.fstat(self.lock)
            require(stat.S_ISREG(item.st_mode) and item.st_uid == 0 and item.st_gid == 0 and item.st_nlink == 1
                    and stat.S_IMODE(item.st_mode) == 0o600, "TRANSACTION_LOCK_REFUSED")
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.checkpoint = Checkpoint(STATE)
            self.signal_before = signal.signal(signal.SIGALRM,self.timeout)
        except BaseException:
            os.close(self.lock)
            self.lock = None
            raise
        return self

    def __exit__(self,*_):
        signal.setitimer(signal.ITIMER_REAL,0)
        if self.signal_before is not None:
            signal.signal(signal.SIGALRM,self.signal_before)
        # Only our matching lease can be removed. An interrupted process leaves
        # a stale lease, which the boot generator rejects by PID/start ticks.
        try:
            path = VOLATILE/"active.json"
            if path.exists() and private_read(path) == self.lease():
                path.unlink()
                sync_directory(VOLATILE)
        finally:
            if self.lock is not None:
                os.close(self.lock)
                self.lock = None

    @staticmethod
    def timeout(*_):
        raise Refused("CUTOVER_TIME_BUDGET_EXHAUSTED")

    @staticmethod
    def lease():
        raw = Path("/proc/self/stat").read_bytes()
        require(len(raw) <= 4096,"LEASE_PROCESS_REFUSED")
        fields = raw[raw.rfind(b")")+2:].split()
        require(len(fields)>19 and fields[19].isdigit(),"LEASE_PROCESS_REFUSED")
        return {"pid":os.getpid(),"start_ticks":fields[19].decode("ascii")}

    def claim_lease(self):
        path = VOLATILE/"active.json"
        if path.exists() or path.is_symlink():
            value = private_read(path)
            # The filesystem lock is exclusive; retain a foreign live lease
            # instead of choosing another process's identity.
            require(value == self.lease() or not self.live_lease(value),"LIVE_TRANSACTION_LEASE_REFUSED")
            publish_private(path,self.lease(),replace=True)
        else:
            publish_private(path,self.lease())

    @staticmethod
    def live_lease(value):
        require(type(value) is dict and set(value)=={"pid","start_ticks"}
                and type(value["pid"]) is int and value["pid"]>1
                and type(value["start_ticks"]) is str and value["start_ticks"].isdigit(),"LEASE_DOCUMENT_REFUSED")
        path=Path("/proc")/str(value["pid"])
        try:
            if path.stat().st_uid != 0:
                return False
            raw=(path/"stat").read_bytes()
            fields=raw[raw.rfind(b")")+2:].split()
            return len(raw)<=4096 and len(fields)>19 and fields[19].decode("ascii")==value["start_ticks"]
        except FileNotFoundError:
            return False

    def remaining(self):
        if self.started is None or self.holding:
            return None
        returning = self.recovering or self.checkpoint.read() in (Phase.RETURNING,Phase.RETURNED)
        limit=10800 if returning else 5400
        remaining=limit-(self.clock()-self.started)
        require(remaining>0,"CUTOVER_TIME_BUDGET_EXHAUSTED")
        return remaining

    def arm_deadline(self):
        remaining=self.remaining()
        signal.setitimer(signal.ITIMER_REAL,remaining or 0)

    def timed_run(self,args,**kwargs):
        remaining=self.remaining()
        if remaining is not None:
            kwargs["timeout"]=min(kwargs.get("timeout",30),remaining)
        return self.run(args,**kwargs)

    def command(self,args,timeout=30,capture=False,maximum=65536):
        try:
            process=self.timed_run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,env={"LANG":"C","LC_ALL":"C"},timeout=timeout,check=False)
        except (OSError,subprocess.TimeoutExpired):
            raise Refused("SEALED_OPERATION_REFUSED") from None
        require(process.returncode==0,"SEALED_OPERATION_REFUSED")
        if capture:
            require(len(process.stdout)<=maximum,"SEALED_RESULT_SIZE_REFUSED")
            return process.stdout
        return None

    def helper(self,name):
        require(name in HELPERS,"HELPER_REFUSED")
        path=self.release.helpers[name]
        args=[self.release.tools["python"],"-I","-S",path] if path.endswith(".py") else [path]
        return strict_json(self.command(args,timeout=1800 if name=="forgejo_governance" else 240,capture=True),65536)

    def verify_artifacts(self):
        closure=self.command([self.release.tools["nix_store"],"--query","--requisites",*sorted(self.release.roots)],
                             timeout=120,capture=True,maximum=1048576)
        try:
            closure=closure.decode("ascii","strict").splitlines()
        except UnicodeError:
            raise Refused("ARTIFACT_CLOSURE_REFUSED") from None
        require(closure and all(STORE.fullmatch(path) for path in closure)
                and len(closure)==len(set(closure)) and set(closure)==set(self.release.artifacts),
                "ARTIFACT_CLOSURE_CHANGED")
        paths=sorted(self.release.artifacts)
        for begin in range(0,len(paths),64):
            selected=paths[begin:begin+64]
            value=strict_json(self.command([self.release.tools["nix"],"--extra-experimental-features","nix-command",
                                          "path-info","--json",*selected],
                                          timeout=120,capture=True,maximum=1048576))
            if type(value) is list:
                require(all(type(v) is dict and type(v.get("path")) is str for v in value),"ARTIFACT_METADATA_REFUSED")
                require(len({v["path"] for v in value})==len(value),"ARTIFACT_DUPLICATE_METADATA_REFUSED")
                value={v["path"]:v for v in value}
            require(type(value) is dict and set(value)==set(selected),"ARTIFACT_SET_CHANGED")
            for path in selected:
                require(type(value[path]) is dict and value[path].get("narHash")==self.release.artifacts[path],
                        "ARTIFACT_HASH_CHANGED")
            # path-info alone checks the registration, not the current bytes.
            self.command([self.release.tools["nix_store"],"--verify-path",*selected],timeout=900)

    def verify_identities(self):
        for name,expected in RETAINED_IDENTITIES.items():
            try:
                entry=pwd.getpwnam(name)
            except KeyError:
                raise Refused("RETAINED_IDENTITY_MISSING") from None
            require((entry.pw_uid,entry.pw_gid)==expected,"RETAINED_IDENTITY_CHANGED")
        for number in range(940,949):
            for lookup in (pwd.getpwuid,grp.getgrgid):
                try:
                    lookup(number)
                except KeyError:
                    continue
                raise Refused("RESERVED_IDENTITY_ALREADY_PRESENT")

    def verify_guard_binding(self):
        for generation in (self.generations.staged,self.generations.promoted):
            path=generation+"/etc/systemd/system-generators/mrjam-first-cutover-guard"
            require(os.path.realpath(path)==self.release.generator,"GENERATION_GUARD_BINDING_CHANGED")

    def verify_credentials(self):
        parent=Path("/var/lib/mrjam-identite")
        private_directory(parent)
        for name in REQUIRED_PRIVATE:
            entry=(parent/name).lstat()
            require(stat.S_ISREG(entry.st_mode) and entry.st_uid==entry.st_gid==0 and entry.st_nlink==1
                    and stat.S_IMODE(entry.st_mode)==0o600 and 0<entry.st_size<=65536,"REQUIRED_CREDENTIAL_REFERENCE_REFUSED")
        value=self.helper("capabilities")
        require(type(value) is dict and value.get("all_tokens_present") is True and value.get("tokens_distinct") is True,
                "WORKER_CREDENTIALS_MISSING")
        expected={"admission":(True,True,False),"cycle":(False,True,False),"replay":(False,False,True)}
        for name,memberships in expected.items():
            entry=value.get(name)
            require(type(entry) is dict and entry.get("present") is True and entry.get("authenticated_service") is True
                    and tuple(entry.get(k) for k in ("onboarding_membership","mail_read_membership","people_admin_membership"))==memberships,
                    "WORKER_CREDENTIAL_CAPABILITY_REFUSED")

    def verify_source_inputs(self):
        value=self.helper("forgejo_sources")
        require(value=={"schema_version":1,"binding_sha256":self.release.forgejo_binding,"source_inputs_verified":True},
                "FORGEJO_SOURCE_INPUTS_NOT_VERIFIED")
        root=Path("/var/lib/mrjam-source-import")
        private_directory(root)
        total=0
        for name in SOURCE_REPOSITORIES:
            entry=(root/(name+".bundle")).lstat()
            require(stat.S_ISREG(entry.st_mode) and entry.st_uid==entry.st_gid==0 and entry.st_nlink==1
                    and stat.S_IMODE(entry.st_mode) in (0o400,0o600) and 0<entry.st_size<=64*1024**3,
                    "FORGEJO_SOURCE_STAGING_CHANGED")
            total+=entry.st_size
        self.source_archive_bytes=total

    def verify_capacity(self):
        # Names and sizes are consumed privately; no per-file inventory escapes.
        require(self.saved is not None,"SNAPSHOT_DESTINATION_REQUIRED")
        self.saved.verify_storage([name for name in ROOTS if self.saved.source(name) is not None])
        total=0
        entries=0
        deadline=self.clock()+120
        def unreadable(_):
            raise Refused("STATE_CAPACITY_UNREADABLE")
        for name in ROOTS:
            root=Path("/var/lib")/name
            try:
                item=root.lstat()
            except FileNotFoundError:
                require(name not in REQUIRED,"REQUIRED_STATE_MISSING")
                continue
            require(stat.S_ISDIR(item.st_mode),"STATE_ROOT_REFUSED")
            for directory,folders,files in os.walk(root,followlinks=False,onerror=unreadable):
                for child in folders+files:
                    metadata=(Path(directory)/child).lstat()
                    entries+=1
                    total+=metadata.st_size+4096
                    require(entries<=2000000 and self.clock()<deadline,"STATE_CAPACITY_SCAN_LIMIT")
        # Retain snapshot/return space and a private Git ancestry copy (including
        # a possible repack). New source packs need destination + temporary-copy
        # space beyond their already staged archives. Closures are already here.
        require(shutil.disk_usage("/var/lib").free>=total*3+self.source_archive_bytes*2+2*1024**3,
                "COHERENT_RETURN_CAPACITY_REQUIRED")

    def closed_status(self,host,path="/",port=443):
        require(host in DOMAINS and port==443 and path in ("/","/status.php","/api/healthz","/readyz","/healthz"),
                "HTTP_TARGET_REFUSED")
        args=[self.release.tools["curl"],"--silent","--show-error","--noproxy","*","--max-time","5",
              "--cacert",self.release.ca_file,"--resolve",host+":"+str(port)+":127.0.0.1",
              "--output","/dev/null","--write-out","%{http_code}","https://"+host+":"+str(port)+path]
        raw=self.command(args,timeout=8,capture=True,maximum=3)
        require(re.fullmatch(rb"[1-5][0-9]{2}",raw),"HTTP_STATUS_REFUSED")
        return int(raw)

    def previous_http(self):
        value={host:self.closed_status(host) for host in DOMAINS}
        require(all(200<=status<=599 for status in value.values()),"PREVIOUS_HTTP_OBSERVATION_REFUSED")
        return value

    def wait_previous_http(self):
        # A successful Type=simple start does not prove that its HTTPS socket
        # already accepts connections. Retry only a failed transport operation;
        # a received HTTP status must still match the original observation.
        # Start no new observation after 30 seconds. An observation already
        # started has at most eight separately bounded 8-second subprocesses;
        # the global return deadline continues to bound calls and sleeps.
        deadline=self.clock()+30
        while True:
            self.remaining()
            require(self.clock()<deadline,"PREVIOUS_PRIVATE_HTTP_NOT_RESTORED")
            try:
                value=self.previous_http()
            except Refused as error:
                if error.args!=("SEALED_OPERATION_REFUSED",):
                    raise
            else:
                require(value==self.original["http_status"],"PREVIOUS_PRIVATE_HTTP_NOT_RESTORED")
                return
            remaining=self.remaining()
            delay=min(0.25,deadline-self.clock(),remaining if remaining is not None else 0.25)
            require(delay>0,"PREVIOUS_PRIVATE_HTTP_NOT_RESTORED")
            self.sleep(delay)

    def validate_initial_record(self,value):
        require(type(value) is dict and set(value)=={"schema_version","release_sha256","active_units","foreign_masks",
                "runtime_mask_intent","http_status"} and type(value["schema_version"]) is int
                and value["schema_version"]==1 and value["release_sha256"]==self.release.digest,"RECOVERY_RELEASE_MISMATCH")
        for key in ("active_units","foreign_masks","runtime_mask_intent"):
            require(type(value[key]) is list and all(type(unit) is str for unit in value[key])
                    and value[key]==sorted(set(value[key])) and set(value[key])<=ALLOWED,
                    "RECOVERY_UNIT_RECORD_REFUSED")
        require(not (set(value["active_units"]) & set(value["foreign_masks"])),"RECOVERY_MASK_RECORD_CONFLICT")
        require(set(value["runtime_mask_intent"])==ALLOWED-set(value["foreign_masks"]),"RECOVERY_MASK_INTENT_CHANGED")
        require(type(value["http_status"]) is dict and set(value["http_status"])==set(DOMAINS)
                and all(type(v) is int and 200<=v<=599 for v in value["http_status"].values()),
                "RECOVERY_HTTP_RECORD_REFUSED")

    def prepare_preflight_retry(self):
        """Discard only interrupted metadata writes before any transaction effect.

        Initial metadata is committed before PREPARED; a SIGKILL in that window
        must not strand an otherwise untouched host. The next full preflight
        observes the live old system again, rather than trusting its old record.
        A selected staged boot, gate, mask, snapshot or durable phase forbids it.
        """
        absent=lambda path:not path.exists() and not path.is_symlink()
        require(absent(STATE/"phase.json") and absent(STATE/"adoption-started.json"),"EXISTING_RELEASE_STATE_REFUSED")
        self.generations.verify_previous()
        require(all(absent(path) for path in (VOLATILE/"masks.json",VOLATILE/"masks.next",
                GENERATOR_DIRECTORY/GENERATOR_NAME)),"PREFLIGHT_TRANSACTION_EFFECT_REFUSED")
        require(set(os.listdir(STATE))<={"transaction.lock","initial.json","initial.json.next","phase.next","snapshot"},
                "PREFLIGHT_STATE_CONTENT_REFUSED")
        if (STATE/"snapshot").exists() or (STATE/"snapshot").is_symlink():
            private_directory(STATE/"snapshot")
            require(not os.listdir(STATE/"snapshot"),"PREFLIGHT_SNAPSHOT_EXISTS")
        require(self.control.execute([self.release.tools["nft"],"list","table","inet",GATE_NAME],accepted=(0,1))==1,
                "PREFLIGHT_TRANSACTION_EFFECT_REFUSED")
        if not absent(VOLATILE/"active.json"):
            active=VOLATILE/"active.json"
            if active.lstat().st_nlink==2:
                pending=VOLATILE/"active.json.next"
                require(not pending.is_symlink(),"PREFLIGHT_PENDING_METADATA_REFUSED")
                require((active.lstat().st_dev,active.lstat().st_ino)==(pending.lstat().st_dev,pending.lstat().st_ino),
                        "PREFLIGHT_PENDING_METADATA_REFUSED")
            require(not self.live_lease(private_read(active,links=(1,2))),"LIVE_TRANSACTION_LEASE_REFUSED")
        # A killed link+unlink publish may leave two names for the same inode.
        # Only these uncommitted metadata names may be removed, after the
        # no-effects proof; never clean a snapshot, phase or application path.
        for pending,target in ((STATE/"initial.json.next",STATE/"initial.json"),
                               (STATE/"phase.next",None),(VOLATILE/"active.json.next",VOLATILE/"active.json")):
            if absent(pending):
                continue
            item=pending.lstat()
            require(stat.S_ISREG(item.st_mode) and item.st_uid==item.st_gid==0
                    and stat.S_IMODE(item.st_mode)==0o600 and item.st_size<=65536
                    and item.st_nlink in (1,2),"PREFLIGHT_PENDING_METADATA_REFUSED")
            if item.st_nlink==2:
                require(target is not None and not target.is_symlink(),"PREFLIGHT_PENDING_METADATA_REFUSED")
                other=target.lstat()
                require((item.st_dev,item.st_ino)==(other.st_dev,other.st_ino),"PREFLIGHT_PENDING_METADATA_REFUSED")
            pending.unlink()
            sync_directory(pending.parent)
        if not absent(STATE/"initial.json"):
            self.validate_initial_record(private_read(STATE/"initial.json"))
            return True
        return False

    def verify_staging_absent(self):
        # The staging writers use exclusive mkdir after the paired snapshot.
        # A previous attempt's material needs separate retention, never cleanup
        # here or a late failure after otherwise healthy services were frozen.
        for path in STAGING_DIRECTORIES:
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            raise Refused("EXISTING_ADOPTION_STAGING_REFUSED")

    def preflight(self):
        require(self.lock is not None and self.checkpoint is not None,"TRANSACTION_CONTEXT_REQUIRED")
        require(os.uname().nodename==HOST,"HOST_TARGET_CHANGED")
        self.verify_staging_absent()
        replace_initial=self.prepare_preflight_retry()
        self.verify_artifacts()
        self.verify_guard_binding()
        self.verify_identities()
        self.verify_credentials()
        self.verify_source_inputs()
        private_directory(STATE/"snapshot",True)
        self.saved=DeadlineSnapshot(self)
        self.verify_capacity()
        require(not (Path("/var/lib/nextcloud-php-security/blocked")).exists(),"NEXTCLOUD_CONTAINMENT_ACTIVE")
        self.control.observe()
        foreign=sorted(self.control.foreign_masks)
        require(not (self.control.active_before & set(foreign)),"ACTIVE_FOREIGN_MASK_REFUSED")
        before=self.previous_http()
        self.original={"schema_version":1,"release_sha256":self.release.digest,"active_units":sorted(self.control.active_before),
                       "foreign_masks":foreign,"runtime_mask_intent":sorted(ALLOWED-set(foreign)),"http_status":before}
        publish_private(STATE/"initial.json",self.original,replace=replace_initial)
        self.claim_lease()

    def freeze(self):
        require(self.original is not None,"INITIAL_STATE_REQUIRED")
        if self.started is None:
            self.started=self.clock()
        self.arm_deadline()
        # Boot only: no live switch or state migration precedes this operation.
        if not self.boot_selected:
            self.generations.select_boot(self.generations.staged)
            self.boot_selected=True
        self.control.freeze()

    def verify_quiescent(self):
        self.control.verify_quiescent()

    def verify_obligations(self):
        value=self.helper("obligations")
        require(type(value) is dict,"HISTORICAL_OBLIGATION_PROBE_REFUSED")
        for name in ("cycle","closure"):
            entry=value.get(name)
            require(type(entry) is dict and entry.get("state")=="observed"
                    and entry.get("markers_present") is False,"HISTORICAL_OBLIGATION_REQUIRES_ADOPTION")
        require(value["closure"].get("incomplete_present") is False,"INCOMPLETE_CLOSURE_REQUIRES_ADOPTION")
        for relative in LEGACY_JOURNALS:
            path=Path("/var/lib/mrjam-metier")/relative
            require(not path.exists() and not path.is_symlink(),"HISTORICAL_JOURNAL_REQUIRES_ADOPTION")

    def snapshot(self):
        self.verify_quiescent()
        self.verify_obligations()
        self.saved.create()

    def verify_snapshot(self):
        self.saved.verify()

    def install_candidate(self):
        require(self.checkpoint.read()==Phase.SNAPSHOT,"SNAPSHOT_CHECKPOINT_REQUIRED")
        publish_private(STATE/"adoption-started.json",{"schema_version":1,"release_sha256":self.release.digest})
        try:
            self.generations.activate(self.generations.staged)
        finally:
            self.control.close_ingress()
        self.verify_quiescent()

    def adopt_private_state(self):
        require(self.checkpoint.read()==Phase.CANDIDATE,"CANDIDATE_CHECKPOINT_REQUIRED")
        self.verify_quiescent()
        self.verify_obligations()
        stage_credentials.prepare()
        stage_adoption.prepare()
        self.control.start(FILE_ADOPTIONS)
        self.control.release_masks(DATABASE)
        self.control.start(("postgresql.service",))
        self.control.start(SQL_ADOPTIONS)

    def start_private_services(self):
        require(self.checkpoint.read()==Phase.ADOPTED,"ADOPTED_CHECKPOINT_REQUIRED")
        self.control.start(PRIVATE_SERVICES)
        self.control.start(("mrjam-forgejo-bootstrap.service",))
        probe=self.helper("forgejo_probe")
        require(type(probe) is dict and probe.get("technical_account_eligible") is True and probe.get("technical_account_attested") is True
                and probe.get("api_admin") is True and probe.get("temporary_token_revoked") is True,
                "FORGEJO_TECHNICAL_BOOTSTRAP_REFUSED")
        # This separately sealed operation must actually import/adopt the real
        # source revisions and protected policy. A local test receipt or newly
        # created empty repositories cannot satisfy this precondition.
        value=self.helper("forgejo_governance")
        require(value=={"schema_version":1,"binding_sha256":self.release.forgejo_binding,"sources_bound":True,
                        "protected_policy_verified":True,"temporary_credentials_revoked":True},
                "FORGEJO_RELEASE_AUTHORITY_NOT_ESTABLISHED")
        self.helper("forgejo_cleanup")

    def ready(self,port,host,expected):
        require((port,host) in ((3002,"vision.mrj.am"),(38101,"vision.mrj.am")),"READINESS_TARGET_REFUSED")
        raw=self.command([self.release.tools["curl"],"--silent","--show-error","--fail","--noproxy","*",
                          "--max-time","10","--header","Host: "+host,"http://127.0.0.1:"+str(port)+"/readyz"],
                         timeout=12,capture=True,maximum=8192)
        require(strict_json(raw,8192)==expected,"PRIVATE_READINESS_REFUSED")

    def verify_private_services(self):
        self.ready(3002,"vision.mrj.am",{"status":"ready"})
        self.ready(38101,"vision.mrj.am",{"status":"ready","scope":"configured-capabilities-only","capabilities":list(READY_CAPABILITIES)})
        sso=self.helper("forgejo_sso")
        require(type(sso) is dict and sso.get("passed") is True and sso.get("mutation_performed") is False
                and sso.get("private_values_exported") is False,"FORGEJO_SSO_CONTINUITY_REFUSED")
        require(self.closed_status("forge.mrj.am","/api/healthz")==200,"FORGEJO_PRIVATE_HEALTH_REFUSED")
        require(self.closed_status("cloud.mrj.am","/status.php")==200,"NEXTCLOUD_PRIVATE_HEALTH_REFUSED")
        for unit in PRIVATE_SERVICES:
            # Projection/setup units may be successful inactive oneshots.
            values=self.control.properties(unit)
            require(values["ActiveState"]=="active" or (values["ActiveState"]=="inactive"
                    and unit in ("mrjam-identity-aliases.service","nextcloud-setup.service")),
                    "PRIVATE_SERVICE_NOT_RUNNING")
        for unit in PUBLIC_TIMERS:
            require(self.control.properties(unit)["ActiveState"] in ("inactive","failed"),"PUBLIC_TIMER_STARTED_EARLY")

    def open_public_writes(self):
        require(self.checkpoint.read()==Phase.OPENING,"DURABLE_OPENING_REQUIRED")
        self.generations.select_boot(self.generations.promoted)
        try:
            self.generations.activate(self.generations.promoted)
        finally:
            self.control.close_ingress()
        # Adoption units stay masked. The changed admission configuration is
        # explicitly restarted; restartIfChanged=false does not do this for us.
        self.control.stop(("mrjam-vision-admission.service",))
        self.control.wait_stopped(("mrjam-vision-admission.service",))
        self.control.release_masks(TIMER_SERVICES)
        self.control.start(PRIVATE_SERVICES)
        self.control.start(PUBLIC_TIMERS)
        self.control.open_ingress()

    def verify_public_services(self):
        require(self.checkpoint.read()==Phase.OPEN,"PUBLIC_OPEN_CHECKPOINT_REQUIRED")
        require(all(status in (200,301,302,303,307,308) for status in self.previous_http().values()),
                "PROMOTED_PUBLIC_SERVICE_UNAVAILABLE")
        self.ready(38101,"vision.mrj.am",{"status":"ready","scope":"configured-capabilities-only","capabilities":list(READY_CAPABILITIES)})
        require(os.path.realpath("/run/current-system")==self.generations.promoted
                and os.path.realpath("/nix/var/nix/profiles/system")==self.generations.promoted,"PROMOTED_GENERATION_NOT_SELECTED")
        for unit in PUBLIC_TIMERS:
            require(self.control.properties(unit)["ActiveState"]=="active","PROMOTED_TIMER_NOT_RUNNING")

    def restore_snapshot(self):
        require(self.checkpoint.read()==Phase.RETURNING,"RETURN_CHECKPOINT_REQUIRED")
        self.verify_quiescent()
        self.saved.restore()

    def restore_previous_generation(self):
        require(self.checkpoint.read()==Phase.RETURNING,"RETURN_CHECKPOINT_REQUIRED")
        # Keep the guarded staged boot until the old state is verified and
        # RETURNED is durable. A crash during RETURNING must not boot writers
        # and then permit a second snapshot restore over their newer writes.
        try:
            self.generations.activate(self.generations.previous)
        finally:
            self.control.close_ingress()

    def verify_previous_private_services(self):
        require(self.checkpoint.read()==Phase.RETURNING,"RETURN_CHECKPOINT_REQUIRED")
        active=self.control.active_before
        delayed=RETURN_DELAYED | RETURN_OPTIONAL
        self.control.release_masks(tuple(unit for unit in sorted(ALLOWED-delayed-set(self.original["foreign_masks"]))))
        # Restore the original service dependency graph while keeping timer
        # and backup writers masked until the durable RETURNED boundary.
        safe=tuple(unit for unit in sorted(active) if unit not in delayed)
        self.control.start(tuple(unit for unit in DATABASE if unit in safe))
        self.control.start(tuple(unit for unit in safe if unit not in DATABASE))
        self.wait_previous_http()

    def reopen_previous_services(self):
        require(self.checkpoint.read()==Phase.RETURNED,"DURABLE_RETURNED_REQUIRED")
        self.generations.select_boot(self.generations.previous)
        # Private HTTP and durable RETURNED precede reopening. External jobs
        # must then have network access, including normal ACME dependencies.
        self.control.open_ingress()
        active=set(self.control.active_before)-RETURN_OPTIONAL
        timers=tuple(sorted(active & set(TIMERS)))
        targets={RETURN_TIMER_SERVICES[timer] for timer in timers}
        for timer in timers:
            if timer.startswith("acme-renew-"):
                domain=timer.removeprefix("acme-renew-").removesuffix(".timer")
                targets.update(("acme-setup.service","acme-"+domain+".service"))
        self.control.release_masks(tuple(sorted(targets-set(self.original["foreign_masks"]))))
        # RemainAfterExit ACME/bootstrap and backup oneshots are not work to
        # replay. Only their selected timers may trigger them through systemd.
        workers=active & (RETURN_DELAYED-set(TIMERS)-RETURN_TRIGGERED_ONLY)
        self.control.start(tuple(sorted(workers)))
        self.control.start(timers)

    def hold_current_state(self):
        self.holding=True
        signal.setitimer(signal.ITIMER_REAL,0)
        self.control.freeze()
        # A partially reopened return may already have selected the old boot,
        # which has no guard. Preserve its running state, but select the guarded
        # staged boot before the engine durably reports HELD.
        if os.path.realpath("/nix/var/nix/profiles/system")==self.generations.previous:
            self.generations.select_boot(self.generations.staged)

    def preflight_recovery(self):
        require(self.lock is not None and self.checkpoint is not None and os.uname().nodename==HOST,"RECOVERY_CONTEXT_REFUSED")
        require(self.checkpoint.read() in (Phase.PREPARED,Phase.FREEZING,Phase.FROZEN,Phase.SNAPSHOT,
                Phase.CANDIDATE,Phase.ADOPTED,Phase.VERIFIED,Phase.RETURNING),"RECOVERY_PHASE_REFUSED")
        self.original=private_read(STATE/"initial.json")
        value=self.original
        self.validate_initial_record(value)
        require(os.path.realpath("/run/current-system") in self.release.generations.values()
                and os.path.realpath("/nix/var/nix/profiles/system") in self.release.generations.values(),"RECOVERY_GENERATION_CHANGED")
        self.verify_artifacts()
        self.verify_guard_binding()
        self.generations.verify_paths()
        self.recovering=True
        self.control.observed=True
        self.control.active_before=set(value["active_units"])
        self.control.foreign_masks=set(value["foreign_masks"])
        self.control.masked_here=set(value["runtime_mask_intent"])
        self.control.gate_created=self.control.execute([self.release.tools["nft"],"list","table","inet",GATE_NAME],accepted=(0,1))==0
        # Reconstruct ownership from the release-bound durable intent, never
        # from the current generator output. Reinstall the portable generator
        # and the complete closed set before reviving its lease.
        self.control.close_ingress()
        self.control.publish_masks()
        self.claim_lease()
        self.control.execute([self.release.tools["systemctl"],"daemon-reload"])
        self.control.verify_masks()
        private_directory(STATE/"snapshot")
        self.saved=DeadlineSnapshot(self)

    def verify_adoption_not_started(self):
        path=STATE/"adoption-started.json"
        require(not path.exists() and not path.is_symlink(),"EARLY_PHASE_ADOPTION_CONFLICT")

    def adoption_started(self):
        path=STATE/"adoption-started.json"
        if not path.exists() and not path.is_symlink():
            return False
        value=private_read(path)
        require(type(value) is dict and set(value)=={"schema_version","release_sha256"}
                and type(value["schema_version"]) is int and value["schema_version"]==1
                and value["release_sha256"]==self.release.digest,"ADOPTION_MARKER_REFUSED")
        return True


if __name__ == "__main__":
    raise SystemExit(64)
