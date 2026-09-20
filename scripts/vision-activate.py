#!/usr/bin/env python3
"""Activer un candidat Vision préparé, le vérifier et revenir en arrière sinon."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

EXPECTED_IP = "187.77.95.158"
EXPECTED_VERSION = "1.1.0"
SYSTEM_PROFILE = "/nix/var/nix/profiles/system"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args, env=None, visible=False):
    result = subprocess.run(
        [str(arg) for arg in args], env=env,
        stdout=None if visible else subprocess.PIPE,
        stderr=None if visible else subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"{Path(str(args[0])).name} : code {result.returncode}")
    return result.stdout


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def register_system(system):
    run("nix-env", "--profile", SYSTEM_PROFILE, "--set", system)


def detach_current_link(path):
    path = Path(path)
    if path.is_symlink():
        target = os.readlink(path)
        path.unlink()
        return target
    require(not path.exists(), f"{path} existe sans être un lien symbolique")
    return None


def restore_current_link(path, previous_target):
    path = Path(path)
    if path.is_symlink():
        path.unlink()
    else:
        require(not path.exists(), f"{path} existe sans être un lien symbolique")
    if previous_target is None:
        return
    replacement = path.with_name(path.name + ".vision-rollback")
    require(not replacement.exists() and not replacement.is_symlink(),
            f"Lien temporaire inattendu : {replacement}")
    replacement.symlink_to(previous_target)
    os.replace(replacement, path)


def request(url, username=None, password=None, method="GET", body=None):
    headers = {
        "User-Agent": "vision-activation-check/1",
        "Accept": "application/json, text/event-stream",
    }
    if username is not None:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = "Basic " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(65537)
        require(len(body) <= 65536, "Réponse HTTP trop grande")
        return response.status, response.headers, body


def wait_for(check, message, attempts=60):
    last = None
    for _ in range(attempts):
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # Le détail réseau n'inclut aucun secret.
            last = exc
        time.sleep(2)
    raise RuntimeError(message + (f" ({last})" if last else ""))


def verify_http(domain, username, password):
    origin = "https://" + domain
    status, headers, body = request(origin + "/api/v1/health")
    require(status == 401, "L'API accepte une requête anonyme")
    require(headers.get_content_type() == "application/json", "Le refus anonyme n'est pas JSON")
    require(json.loads(body).get("error") == "authentication_required", "Refus anonyme inattendu")
    require(headers.get("WWW-Authenticate", "").startswith("Basic "), "Challenge Basic absent")

    status, _, body = request(origin + "/api/v1/health", username, password)
    if status != 200:
        public_error = "réponse vide"
        if body:
            try:
                public_error = json.loads(body).get("error", "réponse JSON")
            except json.JSONDecodeError:
                public_error = "réponse non JSON"
        raise RuntimeError(f"Santé authentifiée HTTP {status} ({public_error})")
    payload = json.loads(body)
    require(payload.get("status") == "ok" and payload.get("version") == EXPECTED_VERSION,
            "Contenu de santé authentifiée invalide")
    status, _, body = request(origin + "/api/v1/capabilities", username, password)
    capabilities = json.loads(body)
    require(status == 200 and capabilities.get("api") == "vision"
            and capabilities.get("version") == EXPECTED_VERSION,
            "Capacités authentifiées invalides")
    status, _, body = request(origin + "/api/v1/hello", username, password, method="POST")
    require(status == 200 and json.loads(body).get("message") == "World", "Action hello invalide")

    status, headers, body = request(origin + "/mcp")
    require(status == 401, "MCP accepte une requête anonyme")
    require(headers.get_content_type() == "application/json", "Le refus MCP anonyme n'est pas JSON")
    require(json.loads(body).get("error") == "authentication_required", "Refus MCP anonyme inattendu")

    def mcp(method, params, request_id):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }, separators=(",", ":")).encode()
        rpc_status, rpc_headers, rpc_body = request(
            origin + "/mcp", username, password, method="POST", body=payload
        )
        require(rpc_status == 200, f"MCP {method} HTTP {rpc_status}")
        require(rpc_headers.get_content_type() == "application/json", f"MCP {method} non JSON")
        document = json.loads(rpc_body)
        require(document.get("id") == request_id and "error" not in document,
                f"MCP {method} invalide")
        return document["result"]

    initialized = mcp("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "vision-activation-check", "version": "1"},
    }, "initialize")
    require(initialized.get("serverInfo", {}).get("name") == "vision"
            and initialized.get("serverInfo", {}).get("version") == EXPECTED_VERSION,
            "Initialisation MCP invalide")
    tools = mcp("tools/list", {}, "tools-list").get("tools", [])
    require({tool.get("name") for tool in tools} == {
        "search_memory_sheets",
        "list_due_memory_sheets",
        "get_memory_sheet",
        "save_memory_sheet",
        "record_review",
    }, "Liste des outils MCP invalide")
    search = mcp("tools/call", {
        "name": "search_memory_sheets",
        "arguments": {"query": "__vision_activation_probe_no_match__", "limit": 1},
    }, "database-search")
    require(search.get("isError") is False, "Lecture PostgreSQL par MCP invalide")
    return True


def activate(commit, credentials):
    require(os.geteuid() == 0, "Exécution root sur le VPS requise")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Commit invalide")
    require(isinstance(credentials, dict) and set(credentials) == {"username", "password"},
            "Charge d'identifiants invalide")
    username, password = credentials["username"], credentials["password"]
    require(isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username),
            "Identifiant API invalide")
    require(isinstance(password, str) and len(password) >= 24 and "\n" not in password,
            "Mot de passe API invalide")

    state = Path("/root/vision-deployments") / commit
    report = json.loads((state / "prepared.json").read_text())
    require(report["commit"] == commit and report["activated"] is False, "Préparation incohérente")
    require(report["app_version"] == EXPECTED_VERSION, "Version préparée inattendue")
    require(not (state / "committed.json").exists(), "Candidat déjà activé")
    old_system, old_boot = report["old_system"], report["old_boot"]
    candidate, domain = report["candidate"], report["domain"]
    require(str(Path("/run/current-system").resolve()) == old_system, "Génération active modifiée depuis la préparation")
    require(str(Path(SYSTEM_PROFILE).resolve()) == old_boot, "Génération de démarrage modifiée")
    require(sha256("/etc/nixos/configuration.nix") == report["configuration_sha256"],
            "Configuration NixOS modifiée depuis la préparation")
    addresses = {item[4][0] for item in socket.getaddrinfo(domain, 443, socket.AF_INET)}
    require(EXPECTED_IP in addresses, f"{domain} ne pointe pas vers le VPS")

    config = Path("/etc/nixos/configuration.nix")
    backup = state / "configuration.nix.before"
    pointer = f"{{ imports = [ {report['installed']}/hosts/hostinger/configuration.nix ]; }}\n"
    current = Path("/srv/vision/current")
    previous_current = None
    current_detached = False
    switched = False
    try:
        previous_current = detach_current_link(current)
        current_detached = True
        switched = True
        run(Path(candidate) / "bin/switch-to-configuration", "test", visible=True)
        require(all(run("systemctl", "is-active", service).strip() == "active"
                    for service in ("sshd", "nginx", "postgresql", "matheval", "vision")),
                "Un service requis n'est pas actif")

        credential_env = os.environ.copy()
        credential_env.update(VISION_API_USERNAME=username, VISION_API_PASSWORD=password)
        run(Path(candidate) / "sw/bin/vision-set-credentials", env=credential_env)
        credential_env.pop("VISION_API_PASSWORD", None)

        wait_for(lambda: request("http://127.0.0.1:3001/healthz")[0] == 200,
                 "Santé locale Vision indisponible", attempts=30)
        wait_for(lambda: verify_http(domain, username, password),
                 "API HTTPS Vision indisponible", attempts=90)
        run("python3", Path(report["installed"]) / "scripts/probe.py", visible=True)

        temporary = config.with_suffix(".nix.vision-new")
        temporary.write_text(pointer)
        os.chmod(temporary, 0o644)
        os.replace(temporary, config)
        register_system(candidate)
        run(Path(candidate) / "bin/switch-to-configuration", "boot", visible=True)
        require(str(Path(SYSTEM_PROFILE).resolve()) == candidate,
                "La génération candidate n'est pas enregistrée pour le démarrage")
        committed = {
            **report,
            "activated": True,
            "username_sha256": hashlib.sha256(username.encode()).hexdigest(),
        }
        save(state / "committed.json", committed)
        print("ACTIVATION VISION VALIDÉE : " + json.dumps(committed, sort_keys=True), flush=True)
    except Exception:
        if backup.exists():
            temporary = config.with_suffix(".nix.vision-rollback")
            temporary.write_bytes(backup.read_bytes())
            os.chmod(temporary, 0o644)
            os.replace(temporary, config)
        if switched:
            subprocess.run([str(Path(old_system) / "bin/switch-to-configuration"), "test"])
            subprocess.run([
                "nix-env", "--profile", SYSTEM_PROFILE, "--set", old_boot,
            ])
            subprocess.run([str(Path(old_boot) / "bin/switch-to-configuration"), "boot"])
        if current_detached:
            restore_current_link(current, previous_current)
        save(state / "rollback.json", {"commit": commit, "candidate": candidate, "rolled_back": True})
        raise
    finally:
        credentials["password"] = ""
        password = ""


if __name__ == "__main__":
    try:
        activate(sys.argv[1], json.load(sys.stdin))
    except (OSError, RuntimeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(1)
