import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tests'))
from kanidm_delegations import qualifier
from kanidm_reel import EchecQualification

if __name__ == '__main__':
    try:
        paquet = os.environ.get('MRJAM_KANIDM'); curl = os.environ.get('MRJAM_CURL')
        if not paquet or not curl: raise EchecQualification('outils natifs verrouillés requis')
        print(json.dumps(qualifier(paquet, curl), sort_keys=True))
    except EchecQualification as error:
        print(str(error), file=sys.stderr); sys.exit(1)
