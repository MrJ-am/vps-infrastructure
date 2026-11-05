"""Activate a complete tested NixOS release, then route to its prepared server.

The transaction contains only operational metadata. Recovery is local and does
not depend on Forgejo, the runner, or downloading any artifact.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time

import deploy as D
import migrations

PROFILE = "/nix/var/nix/profiles/system"
ENGINE = Path("/etc/mrjam-ci/engine")
PRIMARY = Path("/etc/nginx/nginx.conf")
CONTROL = Path("/etc/systemd/system.control")
CONTROL_NAMES = ["mrjam-ci", "mrjam-delivery", "mrjam-delivery-restore"]


def store_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._-]+", value):
        raise ValueError("Invalid release store path")
    return Path(value)


def current_system():
    return str(Path("/run/current-system").resolve())


def retain(name, value):
    D.symlink(str(store_path(str(value))), Path("/nix/var/nix/gcroots/mrjam-delivery-" + name))


def ensure_gateway_entry():
    # This location remains valid for the original Nginx master and future ones.
    entry = D.STATE / "nginx-entry.conf"
    entry.write_text("include " + str(D.NGINX_CONF) + ";\n")
    entry.chmod(0o644)
    D.symlink(entry, PRIMARY)


def select_controls(directory):
    directory = store_path(str(directory))
    for name in CONTROL_NAMES:
        source = directory / (name + ".service")
        if not source.is_file():
            raise ValueError("Incomplete controller unit package")
        D.symlink(source, CONTROL / source.name)
    retain("control-units", directory)
    D.command(["systemctl", "daemon-reload"])


def activate(system):
    system = store_path(str(system))
    D.command(["nix-env", "--profile", PROFILE, "--set", str(system)], timeout=30)
    D.command([str(system / "bin/switch-to-configuration"), "switch"], timeout=180)
    ensure_gateway_entry()


def migration_holds(plan, root):
    result = set()
    for step in plan["steps"]:
        previous = migrations.receipt(step, root)
        if previous is None or previous["phase"] != "complete":
            result.update(step.get("hold_units", []))
    return sorted(result)


def hold_services(names):
    for name in names:
        directory = CONTROL / (name + ".service.d")
        directory.mkdir(exist_ok=True)
        path = directory / "11-delivery-migration-hold.conf"
        if path.exists():
            raise RuntimeError("Unfinished migration service hold")
        path.write_text("[Unit]\nConditionPathExists=/run/mrjam-delivery/never-release-migration-hold\n")
    if names:
        D.command(["systemctl", "daemon-reload"])
        D.command(["systemctl", "stop", *[name + ".service" for name in names]], timeout=120)


def release_holds(names, start=False):
    for name in names:
        (CONTROL / (name + ".service.d") / "11-delivery-migration-hold.conf").unlink(missing_ok=True)
    if names:
        D.command(["systemctl", "daemon-reload"])
        if start:
            D.command(["systemctl", "start", *[name + ".service" for name in names]], timeout=120)


def restore_slots(slots, restart=True):
    for slot, executable in slots.items():
        changed = D.slot_command(slot) != executable
        D.configure_slot(slot, executable)
        if restart and (changed or not D.probe(slot, "/healthz")):
            D.command(["systemctl", "restart", "mrjam-rust-" + slot + ".service"], timeout=40)


def restore_system(transaction, restart=True):
    release_holds(transaction.get("hold_units", []))
    if transaction.get("old_system"):
        old = transaction["old_system"]
        previous = current_system()
        if restart and (previous != old or transaction.get("activation_started", False)):
            activate(old)
            restart_managed(transaction.get("candidate_system", previous),
                            {"system": old, "managed_units": transaction.get("managed_units", [])},
                            ensure_active=transaction.get("old_active_units", []))
        elif not restart:
            # Boot recovery must select the old generation for the next boot,
            # without starting services recursively inside Before=nginx.
            D.command(["nix-env", "--profile", PROFILE, "--set", old])
            if previous != old:
                D.command([old + "/bin/switch-to-configuration", "boot"], timeout=90)
    if transaction.get("old_engine"):
        D.symlink(transaction["old_engine"], ENGINE)
    if transaction.get("old_controls"):
        select_controls(transaction["old_controls"])
    restore_slots(transaction.get("old_slots", {}), restart=restart)
    ensure_gateway_entry()


def park(transaction, reason):
    # Once writes might have resumed, preserve the new data and stop public
    # application traffic. No automatic restoration can discard those writes.
    try:
        migrations.quiesce(transaction["migration_plan"], transaction.get("active_migrations", []))
    except (OSError, subprocess.SubprocessError):
        pass
    text = D.NGINX_CONF.read_text()
    hosts = r"(?:vision\.mrj\.am|audition\.mrj\.am|log\.mrj\.am|logique\.echos\.systems|principiipetit\.io|vise\.mrj\.am|cloud\.mrj\.am)"
    text = re.sub(r"(server_name\s+" + hosts + r"\s*;)", r"\1\nreturn 503;", text)
    path = D.STATE / "nginx-maintenance.conf"
    path.write_text(text)
    path.chmod(0o644)
    D.symlink(path, D.NGINX_CONF)
    ensure_gateway_entry()
    try:
        D.reload_nginx()
    finally:
        D.atomic_json(D.STATE / "manual-recovery.json", {"revision": transaction["revision"],
                      "reason": reason, "migration_plan": transaction.get("migration_plan")})
        D.record_failure(transaction["revision"])
        (D.STATE / "transaction.json").unlink(missing_ok=True)


def rollback(transaction, reload=True):
    # Restore traffic first; generation/idle-slot recovery may take longer.
    D.atomic_json(D.STATE / "transaction.json", transaction)
    started = time.monotonic()
    if not transaction.get("compatible", True) and transaction.get("writes_resumed", False):
        park(transaction, "writes-may-have-resumed")
        raise RuntimeError("Incompatible data change requires the declared recovery procedure")
    if not transaction.get("compatible", True) and transaction.get("migration_plan"):
        try:
            migrations.recover(transaction["migration_plan"])
        except Exception:
            park(transaction, "migration-recovery-failed")
            raise
    D.symlink(transaction["old_configuration"], D.NGINX_CONF)
    ensure_gateway_entry()
    if reload:
        try:
            D.reload_nginx()
        except subprocess.SubprocessError:
            pass  # An unsuccessful Nginx replacement must still restore NixOS.
    routed = round(time.monotonic() - started, 3)
    reboot = not reload and transaction.get("old_system") and current_system() != transaction["old_system"]
    restore_system(transaction, restart=reload)
    if reboot:
        # Keep the transaction until the previous generation actually boots.
        # Requires=restore prevents databases/apps from starting meanwhile.
        D.command(["systemctl", "reboot", "--no-block"])
        raise RuntimeError("Returning to the previous system generation at boot")
    if reload:
        D.command(["systemctl", "start", "nginx.service"])
        D.reload_nginx()
    old = transaction.get("old_state")
    if old:
        D.atomic_json(D.STATE / "current.json", old)
    else:
        (D.STATE / "current.json").unlink(missing_ok=True)
    D.record_failure(transaction["revision"])
    (D.STATE / "transaction.json").unlink(missing_ok=True)
    (D.STATE / "preparation.json").unlink(missing_ok=True)
    print(json.dumps({"event": "system-rollback", "revision": transaction["revision"],
                      "routing_seconds": routed,
                      "recovery_seconds": round(time.monotonic() - started, 3)}), flush=True)


def template(configuration, slot, revision):
    return configuration.replace("127.0.0.1:38101", "127.0.0.1:" + str(D.PORTS[slot])).replace(
        revision + ":blue", revision + ":" + slot)


def public_check(revision, slot):
    expected = "x-mrjam-deployment: " + revision + ":" + slot
    for host, path in [("vision.mrj.am", "/"), ("principiipetit.io", "/matheval/")]:
        deadline = time.monotonic() + 2
        while True:
            try:
                headers = D.command(["curl", "--silent", "--show-error", "--fail", "--max-time", "0.5",
                                     "--resolve", host + ":443:127.0.0.1", "--dump-header", "-",
                                     "--output", "/dev/null", "https://" + host + path], timeout=1)
                if expected in headers.lower() and "x-mrjam-source: vps-infrastructure" in headers.lower():
                    break
            except (OSError, subprocess.SubprocessError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Public gateway revision or slot mismatch")
            time.sleep(0.05)


def check_public_services():
    for host, path in [("forge.mrj.am", "/"), ("log.mrj.am", "/"), ("audition.mrj.am", "/"),
                       ("logique.echos.systems", "/"), ("vise.mrj.am", "/"), ("cloud.mrj.am", "/status.php")]:
        status = D.command(["curl", "--silent", "--show-error", "--max-time", "2",
                            "--resolve", host + ":443:127.0.0.1", "--output", "/dev/null",
                            "--write-out", "%{http_code}", "https://" + host + path], timeout=3)
        if not (status.isdigit() and 200 <= int(status) < 400):
            raise RuntimeError("Public service unavailable: " + host)


def unit_text(system, name):
    path = Path(system, "etc/systemd/system", name + ".service")
    if not path.is_file():
        return ""
    result = []
    for line in path.read_text().splitlines():
        if line.startswith(("X-RestartIfChanged=", "X-StopIfChanged=")):
            continue
        if line.startswith(("After=", "Requires=")):
            key, value = line.split("=", 1)
            value = " ".join(item for item in value.split() if item != "mrjam-delivery-restore.service")
            if not value:
                continue
            line = key + "=" + value
        result.append(line)
    return "\n".join(result)


def restart_managed(old_system, manifest, ensure_active=()):
    for name in manifest["managed_units"]:
        same = unit_text(old_system, name) == unit_text(manifest["system"], name)
        active = D.command(["systemctl", "show", name + ".service", "-p", "ActiveState", "--value"]) == "active"
        if same and (active or name not in ensure_active):
            continue
        if active or name in ensure_active or name == "mrjam-identity-aliases":
            D.command(["systemctl", "restart", name + ".service"], timeout=60)


def validate_transition(build, manifest, plan, old_state, plan_root=None):
    baseline = json.loads((D.STATE / "baseline.json").read_text())
    old = old_state or baseline
    digests = old.get("schema_digests", baseline.get("schema_digests", {"server": baseline["schema_digest"]}))
    schema_scopes, version_scopes = set(), set()
    for step in plan["steps"]:
        scope = step.get("scope", "server")
        previous = migrations.receipt(step, plan_root) if plan_root is not None else None
        pending = previous is None or previous["phase"] != "complete"
        if pending or previous.get("schema_after") == build["schema_digests"].get(scope):
            schema_scopes.add(scope)
        if pending or previous.get("stateful_after") == manifest["stateful_versions"].get(scope):
            version_scopes.add(scope)
    for scope, previous in digests.items():
        if build["schema_digests"].get(scope) != previous and scope not in schema_scopes:
            raise RuntimeError("Changed schema lacks a tested migration plan: " + scope)
    versions = old.get("stateful_versions", baseline.get("stateful_versions", {}))
    for name, previous in versions.items():
        target = manifest["stateful_versions"][name]
        changed = previous != target
        if name == "postgresql":
            changed = previous.split(".")[0] != target.split(".")[0]
        if changed and name not in version_scopes:
            raise RuntimeError("Stateful service upgrade lacks its tested migration: " + name)


def promote(build):
    output = store_path(build["output"])
    revision = build["revision"]
    if (output / "share/mrjam/source-revision").read_text().strip() != revision:
        raise ValueError("Artifact revision mismatch")
    manifest = json.loads((output / "release.json").read_text())
    if manifest.get("format") != 2 or manifest.get("revision") != revision:
        raise ValueError("Release manifest mismatch")
    for key in ["system", "engine", "controls", "server", "nginx", "postgresql"]:
        store_path(manifest[key])
    plan_path = output / "migrations/plan.json"
    plan = migrations.load(plan_path)
    migrations.authorize(plan, revision, D.STATE / "approved-migrations", root=plan_path.parent)
    current_file = D.STATE / "current.json"
    old_state = json.loads(current_file.read_text()) if current_file.exists() else None
    validate_transition(build, manifest, plan, old_state, plan_root=plan_path.parent)
    compatible = migrations.compatible(plan, root=plan_path.parent)
    if not compatible:
        # A maintenance program must install its write barrier before apply,
        # retain it until final verification, and own a tested recovery command.
        if any(step["driver"] != "program" for step in plan["steps"]):
            raise ValueError("Maintenance requires a tested program")
    old_configuration = str(D.NGINX_CONF.resolve())
    old_slot = D.active_slot(D.NGINX_CONF.read_text())
    new_slot = "green" if old_slot == "blue" else "blue"
    if not D.probe(old_slot):
        raise RuntimeError("Serving version is not ready")
    old_system = current_system()
    old_controls = str((CONTROL / "mrjam-delivery.service").resolve().parent)
    transaction = {"format": 2, "revision": revision, "old_state": old_state,
                   "old_configuration": old_configuration, "old_system": old_system,
                   "candidate_system": manifest["system"], "activation_started": False,
                   "old_engine": str(ENGINE.resolve()), "old_controls": old_controls,
                   "old_slots": {slot: D.slot_command(slot) for slot in D.PORTS},
                   "compatible": compatible, "migration_plan": str(plan_path),
                   "active_migrations": migrations.pending_programs(plan, plan_path.parent),
                   "managed_units": manifest["managed_units"],
                   "hold_units": migration_holds(plan, plan_path.parent),
                   "old_active_units": [name for name in manifest["managed_units"]
                       if D.command(["systemctl", "show", name + ".service", "-p", "ActiveState", "--value"]) == "active"],
                   "writes_resumed": False}
    retain("candidate", output)
    retain("previous-system", old_system)
    for slot, executable in transaction["old_slots"].items():
        retain("retained-" + slot + "-server", executable.split("/bin/")[0])
        retain("retained-" + slot + "-runtime", str(Path(executable.split(" --config ")[1]).parent))
    D.atomic_json(D.STATE / "transaction.json", transaction)
    try:
        migrations.prepare(plan_path, revision, D.STATE / "approved-migrations", build["schema_digests"], manifest["stateful_versions"])
        hold_services(transaction["hold_units"])
        migrations.apply(plan_path, manifest["postgresql"] + "/bin/psql", revision,
                         D.STATE / "approved-migrations", build["schema_digests"], manifest["stateful_versions"], phase="before-system")
        D.configure_slot(new_slot, manifest["server"] + "/bin/mrjam-server serve --config "
                         + manifest["runtimes"][new_slot] + "/runtime.json")
        # Preserve the serving process's exact command across NixOS activation.
        D.configure_slot(old_slot, transaction["old_slots"][old_slot])
        text = Path(manifest["nginx_template"]).read_text()
        staged = D.STATE / ("nginx-staged-" + revision + ".conf")
        staged.write_text(template(text, old_slot, revision))
        staged.chmod(0o644)
        D.command([manifest["nginx"] + "/bin/nginx", "-t", "-c", str(staged)])
        D.symlink(staged, D.NGINX_CONF)
        ensure_gateway_entry()
        select_controls(manifest["controls"])
        transaction["activation_started"] = True
        D.atomic_json(D.STATE / "transaction.json", transaction)
        activate(manifest["system"])
        migrations.apply(plan_path, manifest["postgresql"] + "/bin/psql", revision,
                         D.STATE / "approved-migrations", build["schema_digests"], manifest["stateful_versions"], phase="after-system")
        release_holds(transaction["hold_units"], start=True)
        restart_managed(old_system, manifest)
        D.command(["systemctl", "restart", "mrjam-rust-" + new_slot + ".service"], timeout=40)
        deadline = time.monotonic() + 30
        while not (D.probe(new_slot, "/healthz") and D.probe(new_slot)):
            if time.monotonic() >= deadline:
                raise RuntimeError("Candidate did not become ready")
            time.sleep(0.25)
        D.reload_nginx()
        if not D.probe(old_slot) or not D.probe(new_slot):
            raise RuntimeError("Readiness failed after system activation")
        check_public_services()
        candidate = D.STATE / ("nginx-" + revision + ".conf")
        candidate.write_text(template(text, new_slot, revision))
        candidate.chmod(0o644)
        D.command([manifest["nginx"] + "/bin/nginx", "-t", "-c", str(candidate)])
        started = time.monotonic()
        D.symlink(candidate, D.NGINX_CONF)
        D.reload_nginx()
        public_check(revision, new_slot)
        if not (D.probe(old_slot) and D.probe(new_slot)):
            raise RuntimeError("Immediate readiness check failed")
        # Persist the conservative boundary BEFORE reopening writes. If the
        # process dies during resume, recovery must never discard new writes.
        transaction["writes_resumed"] = True
        D.atomic_json(D.STATE / "transaction.json", transaction)
        state = {**build, "slot": new_slot, "previous_slot": old_slot,
                 "configuration": str(candidate), "previous_configuration": old_configuration,
                 "previous_state": old_state, "system": manifest["system"],
                 "engine": manifest["engine"], "controls": manifest["controls"],
                 "previous_system": old_system, "rollback": transaction,
                 "stateful_versions": manifest["stateful_versions"],
                 "cutover_seconds": round(time.monotonic() - started, 3),
                 "reboot_required": str(Path(old_system, "kernel").resolve())
                    != str(Path(manifest["system"], "kernel").resolve())}
        D.atomic_json(current_file, state)
        migrations.resume(plan_path)
        (D.STATE / "transaction.json").unlink()
        retain("current", output)
        retain("current-system", manifest["system"])
        if old_state:
            retain("previous", old_state["output"])
        print(json.dumps({"event": "system-deployed", "revision": revision,
                          "slot": new_slot, "seconds": state["cutover_seconds"],
                          "reboot_required": state["reboot_required"]}), flush=True)
    except BaseException:
        rollback(transaction)
        raise
