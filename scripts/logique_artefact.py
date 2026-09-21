#!/usr/bin/env python3
"""Vérifier une archive figée ; extraire dist à part, sans publier ni exécuter."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from registry import ROOT, unique_object


def exiger(condition, message):
    if not condition:
        raise ValueError(message)


def verifier(archive, reference):
    contenu = Path(archive).read_bytes()
    exiger(hashlib.sha256(contenu).hexdigest() == reference["sha256"],
           "L'empreinte de l'archive ne correspond pas à la référence.")
    fichiers, noms = {}, set()
    with zipfile.ZipFile(archive) as paquet:
        exiger(sum(f.file_size for f in paquet.infolist()) <= 64 * 1024 * 1024,
               "Archive décompressée trop volumineuse.")
        for entree in paquet.infolist():
            nom = entree.filename
            chemin = PurePosixPath(nom)
            mode = entree.external_attr >> 16
            exiger(nom not in noms and not chemin.is_absolute()
                   and "\\" not in nom and ".." not in chemin.parts
                   and nom.rstrip("/") == str(chemin)
                   and stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR),
                   "Chemin répété, lien ou entrée ZIP non autorisée.")
            noms.add(nom)
            if nom.startswith("dist/") and not entree.is_dir():
                relatif = nom.removeprefix("dist/")
                exiger(not any(p.startswith(".") for p in PurePosixPath(relatif).parts),
                       "Fichier caché interdit dans dist.")
                fichiers[relatif] = paquet.read(entree)
    nom_manifeste = "manifeste-preparation.json"
    exiger(nom_manifeste in fichiers, "Manifeste applicatif absent.")
    manifeste = json.loads(fichiers[nom_manifeste], object_pairs_hook=unique_object)
    for cle in ("application", "style", "signature"):
        exiger(manifeste.get(cle) == reference[cle], f"Révision différente : {cle}")
        exiger(re.fullmatch("[0-9a-f]{40}", reference[cle]) is not None,
               f"Révision non figée : {cle}")
    exiger(manifeste.get("portageComplet") is True, "Portage incomplet.")
    for cle in ("typographieValidee", "hebergementConfirme", "publicationAutorisee"):
        exiger(type(manifeste.get(cle)) is bool, f"État manquant : {cle}")
    empreintes = manifeste.get("empreintes")
    exiger(isinstance(empreintes, dict)
           and set(fichiers) == set(empreintes) | {nom_manifeste},
           "Inventaire de dist incomplet ou surnuméraire.")
    for nom, empreinte in empreintes.items():
        exiger(hashlib.sha256(fichiers[nom]).hexdigest() == empreinte,
               f"Fichier altéré : {nom}")
    exiger({"index.html", "app.js", "course.js", "bridge.js", "video.js",
            "katex/katex.min.js", "katex/katex.min.css",
            "assets/mrjam/Echologo.svg", "assets/mrjam/signature.css"} <= set(fichiers),
           "Une ressource indispensable est absente.")
    return manifeste, fichiers


def exiger_publication(manifeste):
    """Garde minimale ; la validation de tous les autres projets reste requise."""
    for cle in ("portageComplet", "typographieValidee",
                "hebergementConfirme", "publicationAutorisee"):
        exiger(manifeste.get(cle) is True, f"Publication bloquée : {cle}")


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("archive", type=Path)
    options.add_argument("--reference", type=Path, default=ROOT / "operations/logique-artefact.json")
    options.add_argument("--extraire", type=Path)
    args = options.parse_args()
    reference = json.loads(args.reference.read_text(), object_pairs_hook=unique_object)
    manifeste, fichiers = verifier(args.archive, reference)
    if args.extraire:
        args.extraire.mkdir(parents=True, exist_ok=False)
        for nom, contenu in fichiers.items():
            destination = args.extraire / nom
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contenu)
    print(json.dumps({cle: valeur for cle, valeur in manifeste.items()
                      if cle != "empreintes"} | {"fichiersVerifies": len(fichiers)},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
