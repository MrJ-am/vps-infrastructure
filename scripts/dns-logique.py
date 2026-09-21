#!/usr/bin/env python3
"""Relever le DNS public ; aucune modification de zone, aucun ajout AAAA."""
import json
import subprocess
import sys

DOMAINE = "logique.echos.systems"


def relever():
    resultats = {}
    for type_ in ("A", "AAAA", "CNAME", "CAA"):
        resultat = subprocess.run(
            ["dig", "+time=5", "+tries=2", "+short", DOMAINE, type_],
            check=True, text=True, capture_output=True,
        )
        resultats[type_] = sorted(filter(None, resultat.stdout.splitlines()))
    resultats["pretPourACME"] = (
        resultats["A"] == ["187.77.95.158"]
        and not resultats["AAAA"] and not resultats["CNAME"]
    )
    return resultats


if __name__ == "__main__":
    resultat = relever()
    print(json.dumps(resultat, indent=2))
    if "--exiger" in sys.argv and not resultat["pretPourACME"]:
        sys.exit("DNS non prêt : A exact requis, aucun AAAA non vérifié.")
