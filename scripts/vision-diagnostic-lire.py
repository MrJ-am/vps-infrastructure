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
                   r"arguments=[a-zA-Z0-9_:,-]+ result=(?:-?\d+|ok|tool_error)"
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
