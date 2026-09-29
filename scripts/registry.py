#!/usr/bin/env python3
"""Registre partagé par Nginx et les contrôles, sans dépendance Python tierce."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
PREFIX = re.compile(r"(?:/[a-zA-Z0-9_-]+)+\Z")
PATH = re.compile(r"/[a-zA-Z0-9_./-]*\Z")
AUTH_FILE = re.compile(r"/var/lib/(?:[a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+\Z")
REALM = re.compile(r"[a-zA-Z0-9 ._-]{1,64}\Z")


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Clé JSON répétée : {key}")
        obj[key] = value
    return obj


def valid_path(path):
    return isinstance(path, str) and PATH.fullmatch(path) and ".." not in path and "//" not in path


def validate(projects):
    if not isinstance(projects, dict) or not projects:
        raise ValueError("Le registre doit contenir au moins un projet.")
    domains, ports = set(), set()
    commun = {"domain", "aliases", "prefix", "maxBodySize", "probes"}
    for name, site in projects.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ValueError(f"Identifiant de projet invalide : {name}")
        if not isinstance(site, dict):
            raise ValueError(f"{name} : objet attendu.")
        type_site = site.get("type", "proxy")
        statique = type_site == "static"
        natif = type_site == "native"
        required = commun | ({"type", "root"} if statique else {"type"} if natif else {"port", "service"})
        optional = set() if (statique or natif) else {"type", "auth", "privateHealthPath", "browserAuth"}
        if (not required <= set(site)
                or not set(site) <= required | optional):
            raise ValueError(f"{name} : propriétés manquantes ou inconnues.")
        if type_site not in ("proxy", "static", "native"):
            raise ValueError(f"{name} : type de site inconnu.")
        if not isinstance(site["aliases"], list):
            raise ValueError(f"{name} : aliases doit être une liste.")
        for domain in [site["domain"], *site["aliases"]]:
            if not isinstance(domain, str) or not DOMAIN.fullmatch(domain):
                raise ValueError(f"{name} : domaine invalide.")
            if domain in domains:
                raise ValueError(f"Domaine ou alias déjà attribué : {domain}")
            domains.add(domain)
        port = site.get("port")
        if statique:
            if (not isinstance(site["root"], str)
                    or site["root"] != f"/srv/{name}/current" or site["prefix"] != ""):
                raise ValueError(f"{name} : racine statique dédiée et préfixe vide requis.")
        elif natif:
            if site["prefix"] != "":
                raise ValueError(f"{name} : un service NixOS natif occupe la racine de son domaine.")
        else:
            if type(port) is not int or not 1024 <= port <= 65535 or port in ports:
                raise ValueError(f"{name} : port local invalide ou déjà attribué.")
            ports.add(port)
        prefix = site["prefix"]
        if not isinstance(prefix, str) or (prefix and not PREFIX.fullmatch(prefix)):
            raise ValueError(f"{name} : préfixe invalide, utiliser une chaîne vide pour la racine.")
        if not isinstance(site["maxBodySize"], str) or not re.fullmatch(r"[1-9][0-9]*[km]", site["maxBodySize"]):
            raise ValueError(f"{name} : taille maximale invalide.")
        if not (statique or natif) and (not isinstance(site["service"], str) or not re.fullmatch(r"[a-z][a-z0-9-]*", site["service"])):
            raise ValueError(f"{name} : nom de service invalide.")

        if "browserAuth" in site and (type(site["browserAuth"]) is not bool or not site.get("auth") or not (site["domain"] == "mrj.am" or site["domain"].endswith(".mrj.am"))):
            raise ValueError(f"{name} : session mrj.am invalide.")
        if port == 3002:
            raise ValueError("Port 3002 réservé aux sessions mrj.am.")

        auth = site.get("auth")
        private_health = site.get("privateHealthPath")
        if (auth is None) != (private_health is None):
            raise ValueError(f"{name} : auth et privateHealthPath doivent être déclarés ensemble.")
        if auth is not None:
            if not isinstance(auth, dict) or set(auth) != {"prefix", "basicUserFile", "realm"}:
                raise ValueError(f"{name} : configuration d'authentification invalide.")
            auth_prefix = auth["prefix"]
            if (not valid_path(auth_prefix) or not auth_prefix.endswith("/")
                    or not auth_prefix.startswith(prefix + "/")):
                raise ValueError(f"{name} : préfixe protégé invalide.")
            if (not isinstance(auth["basicUserFile"], str)
                    or not AUTH_FILE.fullmatch(auth["basicUserFile"])
                    or ".." in auth["basicUserFile"]):
                raise ValueError(f"{name} : chemin htpasswd invalide.")
            if not isinstance(auth["realm"], str) or not REALM.fullmatch(auth["realm"]):
                raise ValueError(f"{name} : realm d'authentification invalide.")
            if not valid_path(private_health) or private_health.startswith(auth_prefix):
                raise ValueError(f"{name} : chemin de santé privé invalide.")

        if not isinstance(site["probes"], list) or not site["probes"]:
            raise ValueError(f"{name} : contrôles HTTP requis.")
        paths = set()
        for probe in site["probes"]:
            if not isinstance(probe, dict) or not {"path", "status"} <= set(probe) <= {"path", "status", "contentType", "json", "unchanged"}:
                raise ValueError(f"{name} : définition de contrôle invalide.")
            path = probe["path"]
            if (not valid_path(path) or not path.startswith(prefix + "/") or path in paths
                    or path == private_health):
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
