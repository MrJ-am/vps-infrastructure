"""Fixed incident repair: reopen verified previous state, never restore data."""
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time

PACKAGE = "/nix/store/irb47r5zxmffhlklmf2c613gdm8ydb1z-mrjam-first-release-controller-1"
sys.path.insert(0, PACKAGE + "/libexec")
from release_backend import Backend, Release, Refused, require, private_read, private_directory, publish_private, STATE, VOLATILE
from cutover import Phase
from system_control import ALLOWED, DATABASE, GATE_NAME, Refused as SystemRefused

RELEASE_PATH = "/nix/store/rqfxds31bkc0wq2g69pp0nyhk2xgqfzp-mrjam-first-release-binding-1/release.json"
RELEASE_SHA256 = "e8626d9aca0e6a2760e9900f5b3233395ad310a09ea35b01af4b68b627511028"
INCIDENT = STATE / "previous-resume-20261102.json"
HELD_PHASE = STATE / "previous-resume-held-phase-20261102.json"
OPENING = STATE / "previous-resume-opening-20261102.json"
RESULT = Path("/run/mrjam-first-release-status/result.json")
EXPECTED_RESULT = {"schema_version": 1, "code": "COHERENT_RETURN_REQUIRES_RECOVERY", "phase": "held-for-recovery"}
WITNESS = {"schema_version": 1, "release_sha256": RELEASE_SHA256,
           "incident": "first-release-20261102", "returned_observed_epoch": 1793648715,
           "restoration_authorized": False}
CORE = ("postgresql.service", "kanidm.service", "redis-nextcloud.service",
        "phpfpm-nextcloud.service", "forgejo.service", "mrjam-metier.service",
        "vision-embeddings.service", "nginx.service")
# Exact old Unit= mapping observed on this VPS; ACME is deliberately not stem.service.
DOMAINS = ("audition.mrj.am", "cloud.mrj.am", "forge.mrj.am", "log.mrj.am",
           "logique.echos.systems", "principiipetit.io", "vision.mrj.am", "www.principiipetit.io")
TIMER_BINDINGS = {"acme-renew-" + domain + ".timer": "acme-order-renew-" + domain + ".service" for domain in DOMAINS}
TIMER_BINDINGS.update({name + ".timer": name + ".service" for name in (
    "forgejo-backup", "mrjam-sauvegarde", "nextcloud-backup", "nextcloud-cron",
    "postgresqlBackup-matheval", "postgresqlBackup-nextcloud")})


def present(path):
    return path.exists() or path.is_symlink()


def preflight(backend):
    require(os.geteuid() == 0 and os.uname().nodename == "srv1982677", "INCIDENT_TARGET_REFUSED")
    require(os.path.realpath("/run/current-system") == backend.generations.previous, "INCIDENT_GENERATION_REFUSED")
    require(os.path.realpath("/nix/var/nix/profiles/system") in (backend.generations.previous, backend.generations.staged),
            "INCIDENT_BOOT_REFUSED")
    require(private_read(RESULT) == EXPECTED_RESULT, "INCIDENT_RESULT_REFUSED")
    backend.original = private_read(STATE / "initial.json")
    backend.validate_initial_record(backend.original)
    require(backend.adoption_started() is True, "INCIDENT_ADOPTION_MARKER_REFUSED")
    # This directory proves retention occurred, not completion. The witnessed
    # durable RETURNED above supplies that separate fact; no archive is read.
    private_directory(STATE / "snapshot")
    private_directory(STATE / "snapshot" / "candidate-state-retained")
    require(not present(OPENING), "INCIDENT_ALREADY_OPENING")
    phase = backend.checkpoint.read()
    if present(INCIDENT):
        require(private_read(INCIDENT) == WITNESS and phase in (Phase.HELD, Phase.RETURNED), "INCIDENT_BINDING_REFUSED")
    else:
        require(phase == Phase.HELD, "INCIDENT_PHASE_REFUSED")
    if present(HELD_PHASE):
        held = private_read(HELD_PHASE)
    else:
        require(phase == Phase.HELD, "INCIDENT_HELD_EVIDENCE_REQUIRED")
        held = private_read(STATE / "phase.json")
    require(type(held) is dict and set(held) == {"schema_version", "phase", "elapsed_seconds"}
            and type(held["schema_version"]) is int and held["schema_version"] == 1
            and held["phase"] == Phase.HELD.value and type(held["elapsed_seconds"]) is int
            and held["elapsed_seconds"] >= 0, "INCIDENT_HELD_EVIDENCE_REFUSED")
    backend.incident_held_phase = held
    value = private_read(VOLATILE / "masks.json")
    require(type(value) is dict and set(value) == {"schema_version", "units"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and type(value["units"]) is list and value["units"] == sorted(set(value["units"]))
            and set(value["units"]) <= set(backend.original["runtime_mask_intent"]), "INCIDENT_MASKS_REFUSED")
    backend.control.observed = True
    backend.control.foreign_masks = set(backend.original["foreign_masks"])
    backend.control.active_before = set(backend.original["active_units"])
    backend.control.masked_here = set(backend.original["runtime_mask_intent"])
    backend.control.gate_created = backend.control.execute(
        [backend.release.tools["nft"], "list", "table", "inet", GATE_NAME], accepted=(0, 1)) == 0
    require(backend.control.gate_created, "INCIDENT_GATE_REFUSED")
    require(set(CORE) <= ALLOWED and set(TIMER_BINDINGS) <= ALLOWED
            and set(TIMER_BINDINGS.values()) <= ALLOWED, "INCIDENT_INVENTORY_REFUSED")


def resume(backend):
    preflight(backend)
    backend.started = time.monotonic()
    backend.recovering = True
    backend.control.close_ingress()
    backend.claim_lease()
    backend.control.publish_masks()
    if not present(HELD_PHASE):
        publish_private(HELD_PHASE, backend.incident_held_phase)
    if not present(INCIDENT):
        publish_private(INCIDENT, WITNESS)
    # HELD intentionally ignores live leases. Keep NFT and every writer mask
    # while durably restoring the already-witnessed terminal RETURNED phase.
    backend.checkpoint.write(Phase.RETURNED, 0)
    backend.control.execute([backend.release.tools["systemctl"], "daemon-reload"], timeout=60)
    backend.control.verify_masks()
    active = backend.control.active_before
    prerequisites = set(DATABASE)
    # Old Forgejo requires its existing identity unit. Only normal dependency
    # activation is permitted; this helper never starts it directly.
    if "forgejo.service" in active:
        prerequisites.add("forgejo-identity.service")
    backend.control.release_masks(tuple(sorted(prerequisites - backend.control.foreign_masks)))
    for unit in CORE:
        if unit in active:
            backend.control.start((unit,))
    backend.wait_previous_http()
    backend.generations.select_boot(backend.generations.previous)
    publish_private(OPENING, {"schema_version": 1, "release_sha256": RELEASE_SHA256,
                             "phase": Phase.RETURNED.value, "private_http_verified": True})
    backend.control.open_ingress()
    # Failures from here must not close the restored public applications again.
    failed = []
    for timer, service in sorted(TIMER_BINDINGS.items()):
        if timer not in active:
            continue
        try:
            dependencies = {service}
            if timer.startswith("acme-renew-"):
                domain = timer.removeprefix("acme-renew-").removesuffix(".timer")
                dependencies.update(("acme-setup.service", "acme-" + domain + ".service"))
            backend.control.release_masks(tuple(sorted(dependencies - backend.control.foreign_masks)))
            backend.control.start((timer,))
        except SystemRefused:
            failed.append(timer)
    return {"schema_version": 1, "code": "PREVIOUS_PUBLIC_REOPENED" if not failed else "PREVIOUS_PUBLIC_REOPENED_TIMERS_PENDING",
            "phase": Phase.RETURNED.value, "data_restored": False,
            "timers_pending": failed, "vise_left_held": True}


def main():
    try:
        require(len(sys.argv) == 1, "INCIDENT_ARGUMENTS_REFUSED")
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused("INCIDENT_TIMEOUT")))
        signal.alarm(900)
        release = Release.immutable_file(RELEASE_PATH, RELEASE_SHA256)
        with Backend(release) as backend:
            value = resume(backend)
    except BaseException:
        print('{"schema_version":1,"code":"PREVIOUS_PUBLIC_RESUME_REFUSED"}')
        return 1
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
