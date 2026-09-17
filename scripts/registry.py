#!/usr/bin/env python3
"""Registre partagé par Nginx et les contrôles, sans dépendance Python tierce."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
PREFIX = re.compile(r"(?:/[a-zA-Z0-9_-]+)+\Z")


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Clé JSON répétée : {key}")
        obj[key] = value
    return obj


def validate(projects):
    if not isinstance(projects, dict) or not projects:
        raise ValueError("Le registre doit contenir au moins un projet.")
    domains, ports = set(), set()
    required = {"domain", "aliases", "port", "prefix", "maxBodySize", "service", "probes"}
    for name, site in projects.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ValueError(f"Identifiant de projet invalide : {name}")
        if not isinstance(site, dict) or set(site) != required:
            raise ValueError(f"{name} : propriétés manquantes ou inconnues.")
        if not isinstance(site["aliases"], list):
            raise ValueError(f"{name} : aliases doit être une liste.")
        for domain in [site["domain"], *site["aliases"]]:
            if not isinstance(domain, str) or not DOMAIN.fullmatch(domain):
                raise ValueError(f"{name} : domaine invalide.")
            if domain in domains:
                raise ValueError(f"Domaine ou alias déjà attribué : {domain}")
            domains.add(domain)
        port = site["port"]
        if type(port) is not int or not 1024 <= port <= 65535 or port in ports:
            raise ValueError(f"{name} : port local invalide ou déjà attribué.")
        ports.add(port)
        prefix = site["prefix"]
        if not isinstance(prefix, str) or (prefix and not PREFIX.fullmatch(prefix)):
            raise ValueError(f"{name} : préfixe invalide, utiliser une chaîne vide pour la racine.")
        if not isinstance(site["maxBodySize"], str) or not re.fullmatch(r"[1-9][0-9]*[km]", site["maxBodySize"]):
            raise ValueError(f"{name} : taille maximale invalide.")
        if not isinstance(site["service"], str) or not re.fullmatch(r"[a-z][a-z0-9-]*", site["service"]):
            raise ValueError(f"{name} : nom de service invalide.")
        if not isinstance(site["probes"], list) or not site["probes"]:
            raise ValueError(f"{name} : contrôles HTTP requis.")
        paths = set()
        for probe in site["probes"]:
            if not isinstance(probe, dict) or not {"path", "status"} <= set(probe) <= {"path", "status", "contentType", "json", "unchanged"}:
                raise ValueError(f"{name} : définition de contrôle invalide.")
            path = probe["path"]
            if (not isinstance(path, str) or not re.fullmatch(r"/[a-zA-Z0-9_./-]*", path)
                    or ".." in path or "//" in path or not path.startswith(prefix + "/") or path in paths):
                raise ValueError(f"{name} : chemin de contrôle invalide ou répété.")
            paths.add(path)
            if type(probe["status"]) is not int or not 100 <= probe["status"] <= 599:
                raise ValueError(f"{name} : code HTTP invalide.")
            if "json" in probe and not isinstance(probe["json"], dict):
                raise ValueError(f"{name} : résultat JSON attendu invalide.")
            if "unchanged" in probe and type(probe["unchanged"]) is not bool:
                raise ValueError(f"{name} : unchanged doit être un booléen.")
            if "contentType" in probe and not isinstance(probe["contentType"], str):
                raise ValueError(f"{name} : contentType doit être une chaîne.")
    return projects


def load(path=ROOT / "projects.json"):
    return validate(json.loads(Path(path).read_text(), object_pairs_hook=unique_object))


if __name__ == "__main__":
    projects = load()
    print(f"Registre valide : {len(projects)} projet(s), domaines et ports distincts.")
