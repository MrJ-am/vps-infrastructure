#!/usr/bin/env python3
"""Préparer et publier uniquement le serveur MCP Vision, depuis le runner VPS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

REVISION = "61028623566953610750781ab59f236d072c32bd"
BASE = "021078628d8451086c708ed9e63f4722ab1d811f468f4a1e7cd99147fc99d204"
CANDIDAT = "a1688e6dde584fff72ff4f300e6456557a26efc1e5fd716b7e7ba975debf11ea"
RACINE = Path("/root/vision-diagnostic-mcp")
SOURCE = Path(__file__).resolve().parent.parent
COURANT = Path("/srv/vision/current")
ARCHIVE = Path("/srv/vision/incoming") / (REVISION + ".tar.gz")


def executer(*args, **options):
    return subprocess.run([str(a) for a in args], check=True, text=True, **options)


def somme(chemin):
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def preparer():
    RACINE.mkdir(mode=0o700, exist_ok=True)
    ancien = COURANT.resolve()
    assert ancien == Path("/srv/vision/releases/151ab64bd5c9c5c54297e88dbe4d548343cc4928"), ancien
    assert somme(ancien / "src/mcp.lisp") == BASE
    assert somme(SOURCE / "operations/vision-diagnostic-mcp.lisp") == CANDIDAT
    assert executer("systemctl", "is-active", "vision", capture_output=True).stdout.strip() == "active"
    assert not (RACINE / "prepare.json").exists(), "Candidat déjà préparé"
    with tempfile.TemporaryDirectory(dir=RACINE) as temporaire:
        staging = Path(temporaire) / "source"
        shutil.copytree(ancien, staging, symlinks=True)
        shutil.copy2(SOURCE / "operations/vision-diagnostic-mcp.lisp", staging / "src/mcp.lisp")
        (staging / "RELEASE").write_text(REVISION + "\n")
        # Compiler avant toute activation, avec la même commande que vision-release.
        executer("sh", "build.sh", cwd=staging, env={**os.environ, "HOME": temporaire,
                                                    "XDG_CACHE_HOME": temporaire})
        with tarfile.open(ARCHIVE, "w:gz") as archive:
            for chemin in staging.rglob("*"):
                archive.add(chemin, arcname=chemin.relative_to(staging), recursive=False)
    executer("chown", "vision-deploy:vision", ARCHIVE)
    ARCHIVE.chmod(0o600)
    (RACINE / "prepare.json").write_text(json.dumps({"ancien": str(ancien), "revision": REVISION}) + "\n")
    print("Candidat compilé, archive locale préparée ; service inchangé.")


def appel(methode, params=None):
    donnees = json.dumps({"jsonrpc": "2.0", "id": "diagnostic",
                         "method": methode, "params": params or {}}).encode()
    requete = urllib.request.Request("http://127.0.0.1:3001/mcp", data=donnees,
              headers={"Content-Type": "application/json", "X-Vision-Authenticated": "1"})
    with urllib.request.urlopen(requete, timeout=6) as reponse:
        assert reponse.status == 200
        return json.loads(reponse.read())


def activer():
    etat = json.loads((RACINE / "prepare.json").read_text())
    ancien = Path(etat["ancien"])
    assert COURANT.resolve() == ancien, "Version active modifiée : préparation à refaire"
    debut = int(time.time())
    try:
        executer("runuser", "-u", "vision-deploy", "--",
                 "/run/current-system/sw/bin/vision-release", REVISION)
        assert COURANT.resolve() == Path("/srv/vision/releases") / REVISION
        assert somme(COURANT / "src/mcp.lisp") == CANDIDAT
        assert "result" in appel("tools/list")
        refus = appel("tools/call", {"name": "search_memory_sheets",
                                     "arguments": {"query": "sonde-diagnostic", "limit": 0}})
        assert refus["error"]["code"] == -32602
        traces = executer("journalctl", "-u", "vision.service", "--since", "@" + str(debut),
                          "--no-pager", "-o", "cat", capture_output=True).stdout
        assert "method=tools/call tool=search_memory_sheets" in traces
        assert "result=-32602" in traces
        assert "sonde-diagnostic" not in traces, "Une valeur figure dans le journal"
        (RACINE / "actif.json").write_text(json.dumps({"ancien": str(ancien),
                                                        "revision": REVISION}) + "\n")
        print("Vision actif ; appel MCP, erreur attendue et journal sans valeurs vérifiés.")
    except Exception:
        if COURANT.resolve() != ancien:
            suivant = COURANT.with_name("diagnostic-retour")
            suivant.symlink_to(ancien)
            os.replace(suivant, COURANT)
            executer("systemctl", "restart", "vision.service")
        raise


if __name__ == "__main__":
    assert os.geteuid() == 0
    {"preparer": preparer, "activer": activer}[sys.argv[1]]()
