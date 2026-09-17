#!/usr/bin/env python3
"""Valider les réservations PostgreSQL sans contacter le serveur."""
import json
import re
from pathlib import Path

from registry import unique_object

ROOT = Path(__file__).resolve().parents[1]
RESERVED = {"postgres", "template0", "template1", "root", "nobody", "all", "replication"}


def validate(projects):
    if not isinstance(projects, dict):
        raise ValueError("Le registre PostgreSQL doit être un objet.")
    names = set()
    for project, entry in projects.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", project):
            raise ValueError(f"Projet PostgreSQL invalide : {project}")
        if not isinstance(entry, dict) or set(entry) != {"name"}:
            raise ValueError(f"{project} : seul le nom commun base/rôle/compte est attendu.")
        name = entry["name"]
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name)
                or name.startswith("pg_") or name in RESERVED):
            raise ValueError(f"{project} : nom PostgreSQL invalide ou réservé.")
        if name in names:
            raise ValueError(f"Base et rôle déjà attribués : {name}")
        names.add(name)
    return projects


def load(path=ROOT / "databases.json"):
    return validate(json.loads(Path(path).read_text(), object_pairs_hook=unique_object))


if __name__ == "__main__":
    print(f"Registre PostgreSQL valide : {len(load())} base(s), rôles distincts.")
