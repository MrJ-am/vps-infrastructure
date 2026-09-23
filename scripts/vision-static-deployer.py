#!/usr/bin/env python3
"""Publier uniquement les fichiers statiques Vision, avec retour autonome."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

REVISION = sys.argv[2]
assert re.fullmatch(r"[0-9a-f]{40}", REVISION)
DOSSIER = f"/root/vision-static-{REVISION}"
PUBLICATION = f"/srv/vision-interface/releases/{REVISION}"
COURANT = "/srv/vision-interface/current"
UNITE = "vision-static-retour-" + REVISION[:12]


def distant(commande, donnees=None):
    return subprocess.run(["sh", "scripts/connect.sh", commande], input=donnees,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode().strip()


def preparer():
    manifeste = json.loads(Path("artefact/manifest.json").read_text())
    assert manifeste["revisionApplication"] == REVISION
    avant = distant("readlink -f /srv/vision-interface/current")
    assert re.fullmatch(r"/srv/vision-interface/releases/[0-9a-f]{40}", avant), avant
    assert avant != PUBLICATION
    distant(f"test ! -e {shlex.quote(PUBLICATION)} && mkdir -p {shlex.quote(PUBLICATION)}")
    archive = subprocess.run(["tar", "-cf", "-", "-C", "artefact", "."],
                             stdout=subprocess.PIPE, check=True).stdout
    distant(f"tar -xf - -C {shlex.quote(PUBLICATION)} && chmod -R a+rX {shlex.quote(PUBLICATION)}", archive)
    assert json.loads(distant(f"cat {PUBLICATION}/manifest.json")) == manifeste
    distant(f"mkdir -p {DOSSIER}")
    distant(f"printf '%s\\n' {shlex.quote(avant)} > {DOSSIER}/avant")
    print("Artefact contrôlé et préparé ; lien actif intact.")


def activer():
    avant = distant(f"cat {DOSSIER}/avant")
    assert re.fullmatch(r"/srv/vision-interface/releases/[0-9a-f]{40}", avant)
    assert distant(f"readlink -f {COURANT}") == avant, "Interface modifiée depuis la préparation"
    assert json.loads(distant(f"cat {PUBLICATION}/manifest.json"))["revisionApplication"] == REVISION
    retour = ("#!/bin/sh\\nset -eu\\n"
              f"test -f {DOSSIER}/termine && exit 0\\n"
              f"test \\"$(readlink -f {COURANT})\\" = {shlex.quote(PUBLICATION)} || exit 0\\n"
              f"ln -s {shlex.quote(avant)} {DOSSIER}/retour-lien\\n"
              f"mv -Tf {DOSSIER}/retour-lien {COURANT}\\n")
    distant(f"cat > {DOSSIER}/retour.sh && chmod 700 {DOSSIER}/retour.sh", retour.encode())
    distant(f"systemd-run --unit={UNITE} --on-active=15m /bin/sh {DOSSIER}/retour.sh")
    distant(f"ln -s {PUBLICATION} {DOSSIER}/suivant && mv -Tf {DOSSIER}/suivant {COURANT}")
    assert distant(f"readlink -f {COURANT}") == PUBLICATION
    print("Interface activée sous retour autonome.")


def finaliser():
    assert distant(f"readlink -f {COURANT}") == PUBLICATION
    distant(f"touch {DOSSIER}/termine && systemctl stop {UNITE}.timer")
    assert distant(f"readlink -f {COURANT}") == PUBLICATION
    print("Interface enregistrée ; retour autonome désarmé.")


def retour():
    distant(f"/bin/sh {DOSSIER}/retour.sh")


{"preparer": preparer, "activer": activer, "finaliser": finaliser, "retour": retour}[sys.argv[1]]()
