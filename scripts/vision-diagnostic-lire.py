#!/usr/bin/env python3
"""Lire une fenêtre courte de traces MCP en retirant les données réseau privées."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

SOURCE = Path(__file__).resolve().parent.parent
demande = json.loads((SOURCE / "operations/vision-diagnostic-lecture.json").read_text())
assert set(demande) == {"debut", "fin"}
debut = datetime.fromisoformat(demande["debut"].replace("Z", "+00:00"))
fin = datetime.fromisoformat(demande["fin"].replace("Z", "+00:00"))
maintenant = datetime.now(timezone.utc)
assert debut.tzinfo and fin.tzinfo and debut < fin <= maintenant
assert (fin - debut).total_seconds() <= 900 and (maintenant - debut).total_seconds() <= 86400


def lire(*arguments):
    retour = subprocess.run(["journalctl", *arguments,
                             "--since", "@" + str(int(debut.timestamp())),
                             "--until", "@" + str(int(fin.timestamp())),
                             "--no-pager", "-o", "cat"], check=True, text=True,
                            capture_output=True)
    return retour.stdout.splitlines()


motif = re.compile(r"^mcp_trace=\d+ (?:method=[a-z/]+ tool=[a-z_]+ "
                   r"arguments=[a-zA-Z0-9_:,-]+ (?:meta=(?:present|absent) )?"
                   r"result=(?:-?\d+|ok|tool_error)(?: reason=[a-z_]+)?"
                   r"|result=(?:parse_error|invalid_request))$")
appels = [ligne for ligne in lire("-u", "vision.service") if motif.fullmatch(ligne)]
print("Traces JSON-RPC :", len(appels))
for ligne in appels[-100:]:
    print(ligne)

http = []
for ligne in lire("--namespace=http", "-t", "http_acces"):
    try:
        entree = json.loads(ligne)
        if entree.get("site") == "vision.mrj.am" and entree.get("route") == "mcp":
            http.append({cle: entree.get(cle) for cle in
                         ("date", "methode", "route", "statut", "amont",
                          "limite_debit", "limite_connexions")})
    except (ValueError, TypeError):
        pass
print("Requêtes HTTP /mcp :", len(http))
for entree in http[-100:]:
    print(json.dumps(entree, ensure_ascii=False, separators=(",", ":")))

# État du service actif, sans lire ni imprimer de secret utilisateur.
import hashlib
import sqlite3
import urllib.request
service = subprocess.run(["systemctl", "show", "mrj-auth", "-p", "ExecStart", "--value"],
                         check=True, capture_output=True, text=True).stdout
print("Service mrj-auth actif :", subprocess.run(
    ["systemctl", "is-active", "mrj-auth"], check=True, capture_output=True, text=True).stdout.strip())
print("Code authentification déclaré :", "access_tokens" in service or "server.py" in service)
with sqlite3.connect("file:/var/lib/mrj-auth/sessions.sqlite?mode=ro", uri=True) as db:
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    print("Table access_tokens présente :", "access_tokens" in tables)
    if "access_tokens" in tables:
        print("Nombre de tokens actifs :", db.execute(
            "SELECT count(*) FROM access_tokens WHERE revoked IS NULL AND expires > strftime('%s','now')").fetchone()[0])
requete = urllib.request.Request("http://127.0.0.1:3002/auth/mcp",
    headers={"X-Forwarded-Host":"vision.mrj.am","X-Forwarded-Proto":"https"})
try:
    with urllib.request.urlopen(requete, timeout=5) as reponse:
        page = reponse.read(8192).decode("utf-8")
    print("Page active : gestion multi-tokens :", 'Historique et gestion' in page and '/auth/mcp.js' in page)
except Exception as erreur:
    print("Page active indisponible :", type(erreur).__name__)
