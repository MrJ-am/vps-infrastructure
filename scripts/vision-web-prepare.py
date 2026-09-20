#!/usr/bin/env python3
"""Construire et auditer le candidat Vision sur le VPS, sans l'activer."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys

APP_COMMIT = "151ab64bd5c9c5c54297e88dbe4d548343cc4928"
APP_VERSION = "1.3.0"
PREVIOUS_APP_COMMIT = "445f9d7e6944d621de33283ca960d772813f47a2"
PREVIOUS_APP_VERSION = "1.2.0"
DOMAIN = "vision.mrj.am"
RECOVERED_COMMIT = "b71058c99e65aa3d25a8f116cc18d256988a58fd"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args, visible=False, stdout=None):
    result = subprocess.run(
        [str(arg) for arg in args],
        stdout=stdout if stdout is not None else (None if visible else subprocess.PIPE),
        stderr=None if visible else subprocess.PIPE,
        text=stdout is None,
    )
    if result.returncode:
        if visible:
            raise RuntimeError(f"{Path(str(args[0])).name} : code {result.returncode}")
        raise RuntimeError(
            f"{Path(str(args[0])).name} : code {result.returncode} : "
            f"{(result.stderr or '').strip()[:1000]}"
        )
    return result.stdout


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable(name):
    path = shutil.which(name)
    require(path is not None, f"Executable requis introuvable : {name}")
    return Path(path).resolve()


def evaluate(source, configuration, nixpkgs):
    return json.loads(run(
        "nix-instantiate", "--eval", "--strict", "--json",
        source / "scripts/vision-config.nix",
        "--argstr", "configuration", configuration,
        "-I", "nixpkgs=" + nixpkgs,
    ))


def nginx_config_for_test(configuration, temporary):
    """Use an existing TLS pair when a candidate ACME certificate is not issued yet."""
    configuration = Path(configuration)
    temporary = Path(temporary)
    content = configuration.read_text()
    names = ("ssl_certificate", "ssl_certificate_key", "ssl_trusted_certificate")
    entries = {}
    for name in names:
        pattern = re.compile(
            rf"(?m)^(?P<prefix>\s*{name}\s+)(?P<path>[^;\r\n]+)(?P<suffix>;[^\r\n]*)$"
        )
        entries[name] = []
        for match in pattern.finditer(content):
            path = Path(match.group("path").strip())
            require(path.is_absolute(), "Chemin TLS Nginx non absolu")
            entries[name].append((match, path))
    require(entries["ssl_certificate"] and entries["ssl_certificate_key"],
            "Paires TLS Nginx incohérentes")

    missing = [
        (name, match, path)
        for name in names
        for match, path in entries[name]
        if not path.is_file()
    ]
    if not missing:
        return configuration

    fallback = None
    for _, cert_path in entries["ssl_certificate"]:
        if not cert_path.is_file():
            continue
        key_path = next(
            (path for _, path in entries["ssl_certificate_key"]
             if path.is_file() and path.parent == cert_path.parent),
            None,
        )
        trusted_path = next(
            (path for _, path in entries["ssl_trusted_certificate"]
             if path.is_file() and path.parent == cert_path.parent),
            None,
        )
        if key_path is not None and (
                not entries["ssl_trusted_certificate"] or trusted_path is not None):
            fallback = {
                "ssl_certificate": cert_path,
                "ssl_certificate_key": key_path,
                "ssl_trusted_certificate": trusted_path,
            }
            break
    require(fallback is not None, "Aucune paire TLS existante pour contrôler Nginx")

    replacements = []
    for name, match, _ in missing:
        require(fallback[name] is not None,
                "Aucune chaîne TLS existante pour contrôler Nginx")
        replacements.append(
            (match.start("path"), match.end("path"), str(fallback[name]))
        )
    for start, end, value in sorted(replacements, reverse=True):
        content = content[:start] + value + content[end:]
    temporary.write_text(content)
    os.chmod(temporary, 0o600)
    return temporary


def validate_recovery(previous_state, current, session_database):
    """Accepter uniquement le retour complet de la tentative identifiée."""
    require(not (previous_state / "committed.json").exists(), "Le SSO a déjà été enregistré")
    require((previous_state / "rollback-started").exists(), "Retour précédent non engagé")
    rollback = json.loads((previous_state / "rollback.json").read_text())
    require(rollback == {"commit": RECOVERED_COMMIT, "restored": True}, "Retour précédent incomplet")
    prepared = json.loads((previous_state / "prepared.json").read_text())
    require(prepared["commit"] == RECOVERED_COMMIT, "Tentative précédente inconnue")
    for key, value in current.items():
        require(prepared[key] == value, "État modifié après retour : " + key)
    if session_database.exists():
        with sqlite3.connect(session_database.as_uri() + "?mode=ro", uri=True) as database:
            require(database.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0,
                    "Des sessions existent : opération distincte requise")


def prepare(commit):
    require(os.geteuid() == 0, "Exécution root sur le VPS requise")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Commit d'infrastructure invalide")
    os.umask(0o077)
    state = Path("/root/vision-web-deployments") / commit
    source = state / "source"
    require(source.is_dir(), "Archive source absente")
    require(not (state / "prepared.json").exists(), "Ce commit est déjà préparé")

    old_system = str(Path("/run/current-system").resolve())
    old_boot = str(Path("/nix/var/nix/profiles/system").resolve())
    require(old_system == old_boot, "La génération active diffère de la génération de démarrage")
    require(all(run("systemctl", "is-active", service).strip() == "active"
                for service in ("sshd", "nginx", "postgresql", "matheval", "vision")),
            "Un service existant n'est pas actif")
    for database in ("matheval", "vision"):
        timer = "postgresqlBackup-" + database + ".timer"
        require(run("systemctl", "is-active", timer).strip() == "active",
                "Sauvegarde PostgreSQL inactive : " + database)
    print("Timers de sauvegarde Matheval et Vision actifs.", flush=True)
    previous_state = state.parent / RECOVERED_COMMIT
    session_database = Path("/var/lib/mrj-auth/sessions.sqlite")
    if previous_state.exists() or session_database.exists():
        require(previous_state.exists(), "Le SSO existe sans retour identifié")
        validate_recovery(previous_state, {
            "old_system": old_system, "old_boot": old_boot,
            "configuration_sha256": sha256("/etc/nixos/configuration.nix"),
            "credentials_sha256": sha256("/var/lib/vision/auth/htpasswd"),
            "current_release": str(Path("/srv/vision/current").resolve()),
        }, session_database)
        require(subprocess.run(["systemctl", "is-active", "--quiet", "mrj-auth"]).returncode != 0,
                "Le SSO tourne déjà")
        # Le retour validé ne doit pas se redéclencher pendant la nouvelle opération.
        run("systemctl", "stop", "vision-web-rollback-" + RECOVERED_COMMIT[:12] + ".timer")
        for unit in ("vision-web-rollback-", "vision-web-apply-"):
            require(subprocess.run(["systemctl", "is-active", "--quiet", unit + RECOVERED_COMMIT[:12]]).returncode != 0,
                    "Une unité de la tentative précédente tourne encore")
        if session_database.exists():
            shutil.copy2(session_database, state / "sessions.before.sqlite")
        print("Retour précédent contrôlé ; ancien timer désarmé ; aucune session existante.", flush=True)
    nixpkgs = run("nix-instantiate", "--find-file", "nixpkgs").strip()
    require(nixpkgs.startswith("/nix/store/") and Path(nixpkgs).is_dir(), "Nixpkgs installé introuvable")

    installed = Path("/etc/nixos/vps-infrastructure") / commit
    require(not installed.exists(), "Le chemin candidat existe déjà")
    installed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, installed)
    run("sh", installed / "scripts/check.sh", visible=True)

    credential_file = Path("/var/lib/vision/auth/htpasswd")
    require(credential_file.is_file(), "Fichier d’identifiants absent")
    shutil.copy2(credential_file, state / "credentials.before")
    (state / "vision-current.before").write_text(str(Path("/srv/vision/current").resolve()))
    before = evaluate(installed, "/etc/nixos/configuration.nix", nixpkgs)
    after = evaluate(installed, installed / "hosts/hostinger/configuration.nix", nixpkgs)
    require(before["toplevel"] == old_system, "Les sources actives ne reconstruisent pas la génération courante")
    require(before["stable"] == after["stable"], "Un invariant système, PostgreSQL ou Matheval a changé")
    require(before["vision"] is not None and before["vision"]["enabled"] is True,
            "Vision n'est pas actif dans la génération courante")
    require(before["vision"]["domain"] == DOMAIN and before["vision"]["port"] == 3001,
            "Contrat réseau Vision courant inattendu")
    require(before["vision"]["version"] == PREVIOUS_APP_VERSION,
            "Version Vision courante inattendue")
    require(before["vision"]["commit"] == PREVIOUS_APP_COMMIT,
            "Révision Vision courante inattendue")
    require(before["vision"]["databases"] == ["matheval", "vision"],
            "Sauvegardes PostgreSQL courantes incomplètes")
    require(after["vision"]["enabled"] is True, "Le candidat n'active pas Vision")
    require(after["vision"]["domain"] == DOMAIN and after["vision"]["port"] == 3001,
            "Contrat réseau Vision inattendu")
    require(after["vision"]["version"] == APP_VERSION,
            "Version Vision candidate inattendue")
    require(after["vision"]["commit"] == APP_COMMIT, "Révision applicative Vision inattendue")
    require(after["vision"]["databases"] == ["matheval", "vision"], "Sauvegardes PostgreSQL incomplètes")
    require(before["vision"]["service"]["User"] == after["vision"]["service"]["User"] == "vision",
            "Compte système Vision modifié")
    save(state / "config-before.json", before)
    save(state / "config-candidate.json", after)

    shutil.copy2("/etc/nixos/configuration.nix", state / "configuration.nix.before")
    (state / "configuration.sha256").write_text(sha256("/etc/nixos/configuration.nix") + "\n")
    with (state / "matheval-before.dump.age").open("wb") as output:
        run(executable("matheval-backup"), stdout=output)
    with (state / "matheval-before.dump.age").open("rb") as encrypted:
        require(encrypted.read(22) == b"age-encryption.org/v1\n",
                "Sauvegarde Matheval non reconnue comme archive age")
    with (state / "vision-before.dump.age").open("wb") as output:
        run(executable("vision-backup"), stdout=output)
    with (state / "vision-before.dump.age").open("rb") as encrypted:
        require(encrypted.read(22) == b"age-encryption.org/v1\n",
                "Sauvegarde Vision non reconnue comme archive age")

    print("Construction de la génération candidate.", flush=True)
    run(
        "nix-build", "<nixpkgs/nixos>", "-A", "system",
        "-I", "nixpkgs=" + nixpkgs,
        "-I", "nixos-config=" + str(installed / "hosts/hostinger/configuration.nix"),
        "--out-link", state / "result",
        visible=True,
    )
    candidate = str((state / "result").resolve())
    require(candidate == after["toplevel"], "La construction diffère de l'évaluation")
    roots = Path("/nix/var/nix/gcroots/vision-web-deployments") / commit
    roots.mkdir(parents=True, exist_ok=True)
    for name, target in (("previous", old_system), ("candidate", candidate), ("nixpkgs", nixpkgs)):
        (roots / name).symlink_to(target)

    command = shlex.split(after["nginx"]["command"])
    require(command[0] == after["nginx"]["binary"] and "-c" in command,
            "Commande Nginx candidate inattendue")
    nginx_configuration = nginx_config_for_test(
        command[command.index("-c") + 1], state / "nginx-test.conf"
    )
    run(command[0], "-t", "-c", nginx_configuration, visible=True)
    dry_result = subprocess.run(
        [str(Path(candidate) / "bin/switch-to-configuration"), "dry-activate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    require(dry_result.returncode == 0, "Simulation d'activation refusée")
    dry = dry_result.stdout
    require(bool(dry.strip()), "Rapport de simulation vide")
    (state / "dry-activate.txt").write_text(dry)
    print("SIMULATION D'ACTIVATION :\n" + dry, flush=True)

    require(all(run("systemctl", "is-active", service).strip() == "active"
                for service in ("sshd", "nginx", "postgresql", "matheval", "vision")),
            "Un service existant a changé pendant la préparation")
    report = {
        "commit": commit,
        "app_commit": APP_COMMIT,
        "app_version": APP_VERSION,
        "candidate": candidate,
        "old_system": old_system,
        "old_boot": old_boot,
        "nixpkgs": nixpkgs,
        "installed": str(installed),
        "domain": DOMAIN,
        "configuration_sha256": sha256("/etc/nixos/configuration.nix"),
        "matheval_backup": True,
        "vision_backup": True,
        "activated": False,
        "credentials_sha256": sha256(credential_file),
        "current_release": str(Path("/srv/vision/current").resolve()),
        "durable_credentials": any(line.split(":",1)[0] not in ("vision-disabled", "vision-bootstrap-locked") for line in credential_file.read_text().splitlines()),
    }
    save(state / "prepared.json", report)
    print("PRÉPARATION VISION VALIDÉE : " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        prepare(sys.argv[1])
    except (OSError, RuntimeError, ValueError, KeyError, IndexError) as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(1)
