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

# Identifier le code réellement exécuté, sans afficher sa configuration ni ses données.
pid = subprocess.run(["systemctl","show","mrj-auth","-p","MainPID","--value"],
                     check=True,capture_output=True,text=True).stdout.strip()
arguments = Path("/proc",pid,"cmdline").read_bytes().decode().split("\0")
programme = next((Path(a) for a in arguments if a.endswith("/server.py")), None)
if programme and programme.is_file():
    code = programme.read_text()
    print("SHA-256 serveur actif :", hashlib.sha256(code.encode()).hexdigest())
    print("Vérification dans access_tokens :", "SELECT * FROM access_tokens WHERE digest=?" in code)
    print("Route historique seule :", "access_tokens" not in code)
else:
    print("Serveur actif introuvable")
print("Page HTML active (préfixe) :", page[:160].replace("\n"," ") if "page" in globals() else "indisponible")

for cible in ("/run/current-system", "/nix/var/nix/profiles/system", "/etc/nixos/configuration.nix"):
    print("Lien actif", cible, ":", str(Path(cible).resolve()))
for unite in ("mcp-retour-d71dff5858b2.timer", "mcp-appliquer-d71dff5858b2.service"):
    resultat = subprocess.run(["systemctl","show",unite,"-p","ActiveState","-p","Result"],
                              capture_output=True,text=True)
    print("Unité", unite, ":", resultat.stdout.strip().replace("\n"," "))

preparation = Path("/root/mcp-preparations/d71dff5858b221a4eb91655674ab1db74893a5a0")
print("Préparation token :",
      {nom: (preparation / nom).exists() for nom in ("engage","enregistre","retour-engage","retour.json","termine.json")})
if (preparation / "termine.json").exists():
    termine = json.loads((preparation / "termine.json").read_text())
    print("Génération enregistrée token :", termine.get("etat",{}).get("actif"))
print("Import NixOS actif :", Path("/etc/nixos/configuration.nix").read_text()[:300].replace("\n"," "))
