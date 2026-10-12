"""Qualification native locale, aucun accès à une base ou identité de production."""
import json
import os
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE/'tests'))
from kanidm_reel import EchecQualification
from kanidm_politiques import qualifier


if __name__ == '__main__':
    try:
        paquet=os.environ.get('MRJAM_KANIDM'); curl=os.environ.get('MRJAM_CURL')
        if not paquet or not curl: raise EchecQualification('outils natifs verrouillés requis')
        resultat=qualifier(paquet,curl)
        if resultat['assertions'] < 23: raise EchecQualification('assertions incomplètes')
        print(json.dumps(resultat,ensure_ascii=False,sort_keys=True))
    except EchecQualification as err:
        print('Politiques Kanidm : '+str(err),file=sys.stderr);sys.exit(1)
