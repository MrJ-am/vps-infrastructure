#!/usr/bin/env python3
"""Construire les deux candidats sur le VPS ; aucune activation ni publication."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from logique_artefact import exiger


def executer(*arguments, visible=False):
    resultat = subprocess.run([str(a) for a in arguments], text=True, check=True,
                              stdout=None if visible else subprocess.PIPE)
    return resultat.stdout


def enregistrer(chemin, valeur):
    chemin.write_text(json.dumps(valeur, indent=2, ensure_ascii=False) + "\n")


def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def preconditions(source):
    attendu = json.loads((source / "operations/logique-etat-attendu.json").read_text())
    constat = json.loads(executer("sh", source / "scripts/audit-logique.sh"))
    for cle in ("actif", "demarrage", "nixpkgs", "empreinteEntree",
                "matheval", "vision", "cheminMatheval", "cheminVision",
                "certificatLogiquePresent", "publicationLogiquePresente"):
        exiger(constat[cle] == attendu[cle],
               f"État modifié depuis l'audit ({cle}) : nouvel audit nécessaire.")
    exiger(constat["actif"] == constat["demarrage"], "Générations désynchronisées.")
    for unite in ("sshd", "nginx", "postgresql", "matheval", "vision", "mrj-auth",
                  "postgresqlBackup-matheval.timer", "postgresqlBackup-vision.timer"):
        exiger(executer("systemctl", "is-active", unite).strip() == "active",
               f"Unité inactive : {unite}")
    return constat


def evaluer(source, configuration, nixpkgs):
    return json.loads(executer(
        "nix-instantiate", "--eval", "--strict", "--json",
        source / "scripts/logique-config.nix", "--argstr", "configuration", configuration,
        "-I", "nixpkgs=" + nixpkgs))


def preparer(revision):
    exiger(os.geteuid() == 0, "Cette préparation s'exécute sur le VPS depuis Actions.")
    exiger(re.fullmatch("[0-9a-f]{40}", revision) is not None, "Révision Git exacte requise.")
    os.umask(0o077)
    dossier = Path("/root/logique-preparations") / revision
    source = dossier / "source"
    exiger(source.is_dir(), "Sources candidates absentes.")
    exiger(not (dossier / "commence").exists(), "Tentative déjà engagée : conserver ses preuves.")
    avant = preconditions(source)
    (dossier / "commence").touch()
    enregistrer(dossier / "avant.json", avant)
    executer("tar", "-cpf", dossier / "etc-nixos-avant.tar", "-C", "/etc", "nixos")
    shutil.copy2("/etc/nixos/configuration.nix", dossier / "configuration-avant.nix",
                 follow_symlinks=False)
    installe = Path("/etc/nixos/vps-infrastructure") / revision
    exiger(not installe.exists(), "Le répertoire candidat existe déjà.")
    shutil.copytree(source, installe)
    nixpkgs = avant["nixpkgs"]
    reference = evaluer(installe, "/etc/nixos/configuration.nix", nixpkgs)
    exiger(reference["systeme"] == avant["actif"],
           "Les sources installées ne reproduisent pas la génération active.")
    racines = Path("/nix/var/nix/gcroots/logique") / revision
    racines.mkdir(parents=True, exist_ok=False)
    for nom, cible in {"avant": avant["actif"], "nixpkgs": nixpkgs,
                       "python": str(Path(sys.executable).resolve())}.items():
        (racines / nom).symlink_to(cible)

    candidats = {}
    for phase, nom in (("acme", "logique-acme.nix"), ("https", "logique.nix")):
        configuration = installe / "hosts/hostinger" / nom
        candidat = evaluer(installe, configuration, nixpkgs)
        exiger(candidat["invariant"] == reference["invariant"],
               f"Un service, domaine ou invariant existant change dans la phase {phase}.")
        resultat = executer(
            "nix-build", "<nixpkgs/nixos>", "-A", "system",
            "-I", "nixpkgs=" + nixpkgs, "-I", "nixos-config=" + str(configuration),
            "--out-link", racines / phase).strip()
        exiger(resultat == candidat["systeme"], "La génération construite diffère du candidat évalué.")
        # L'amorçage est testé avec les vrais certificats existants ; aucune substitution TLS.
        teste = phase == "acme"
        if teste:
            executer(*shlex.split(candidat["nginx"]), "-t", visible=True)
        candidats[phase] = {"systeme": resultat, "configuration": str(configuration),
                            "nginx": candidat["nginx"], "nginxTeste": teste}

    # Script autonome conservé et vérifié syntaxiquement, jamais exécuté ici.
    # Le futur workflow devra armer son timer AVANT l'essai ACME.
    commandes = {nom: str(Path(shutil.which(nom)).resolve())
                 for nom in ("sh", "flock", "cp", "mv", "touch", "nix-env")}
    q = shlex.quote
    retour = dossier / "retour.sh"
    retour.write_text(f"""#!{commandes['sh']}
set -eu
export PATH={q(os.environ['PATH'])}
export NIX_PATH={q('nixpkgs=' + nixpkgs)}
exec 9>{q(str(dossier / 'bascule.lock'))}
{q(commandes['flock'])} -x 9
test ! -e {q(str(dossier / 'enregistre'))}
{q(commandes['touch'])} {q(str(dossier / 'retour-commence'))}
{q(commandes['cp'])} -a -- {q(str(dossier / 'configuration-avant.nix'))} /etc/nixos/configuration.logique-retour
{q(commandes['mv'])} -Tf -- /etc/nixos/configuration.logique-retour /etc/nixos/configuration.nix
{q(commandes['nix-env'])} --profile /nix/var/nix/profiles/system --set {q(avant['demarrage'])}
{q(avant['actif'] + '/bin/switch-to-configuration')} switch
{q(commandes['touch'])} {q(str(dossier / 'retour-termine'))}
""")
    retour.chmod(0o700)
    executer(commandes["sh"], "-n", retour)
    preconditions(installe)
    bilan = {"revision": revision, "avant": avant, "candidats": candidats,
             "retour": str(retour), "empreinteRetour": empreinte(retour),
             "retourArme": False, "active": False, "publicationAutorisee": False,
             "reste": ["Essai ACME avec timer indépendant",
                       "nginx -t HTTPS avec le nouveau certificat réel",
                       "Validation typographique et de tous les artefacts coordonnés",
                       "Workflow distinct d'activation et de retour applicatif"]}
    enregistrer(dossier / "preparation.json", bilan)
    print(json.dumps(bilan, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage : logique-preparer.py <révision infrastructure>")
    preparer(sys.argv[1])
