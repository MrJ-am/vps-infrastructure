#!/usr/bin/env python3
"""Faire tourner les identifiants Vision et restaurer le hash précédent sinon."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_api(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = urllib.request.Request(
        "https://vision.principiipetit.io/api/v1/health",
        headers={"Authorization": "Basic " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.loads(response.read(65537))
        require(response.status == 200 and body.get("status") == "ok",
                "Les nouveaux identifiants ne donnent pas accès à l'API")


def rotate(credentials):
    require(os.geteuid() == 0, "Exécution root requise")
    require(isinstance(credentials, dict) and set(credentials) == {"username", "password"},
            "Charge d'identifiants invalide")
    username, password = credentials["username"], credentials["password"]
    require(isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username),
            "Identifiant invalide")
    require(isinstance(password, str) and len(password) >= 24 and "\n" not in password,
            "Mot de passe invalide")
    require(subprocess.run(["systemctl", "is-active", "vision"], capture_output=True).returncode == 0,
            "Le service Vision n'est pas actif")

    target = Path("/var/lib/vision/auth/htpasswd")
    require(target.is_file(), "Fichier d'authentification absent")
    descriptor, backup_name = tempfile.mkstemp(prefix=".htpasswd.rollback.", dir=target.parent)
    os.close(descriptor)
    backup = Path(backup_name)
    shutil.copy2(target, backup)
    try:
        environment = os.environ.copy()
        environment.update(VISION_API_USERNAME=username, VISION_API_PASSWORD=password)
        subprocess.run(["/run/current-system/sw/bin/vision-set-credentials"],
                       env=environment, check=True, stdout=subprocess.DEVNULL)
        environment.pop("VISION_API_PASSWORD", None)
        check_api(username, password)
        print(json.dumps({
            "rotated": True,
            "username_sha256": hashlib.sha256(username.encode()).hexdigest(),
        }, sort_keys=True))
    except Exception:
        os.chown(backup, 0, target.stat().st_gid)
        os.chmod(backup, 0o640)
        os.replace(backup, target)
        raise
    finally:
        backup.unlink(missing_ok=True)
        credentials["password"] = ""
        password = ""


if __name__ == "__main__":
    try:
        rotate(json.load(sys.stdin))
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError,
            urllib.error.URLError, subprocess.CalledProcessError) as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(1)
