"""Qualifier uniquement passkeys synthétiques ; diagnostics privés sans sortie de tokens."""
import json
import os
from pathlib import Path
import sys
import traceback

RACINE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RACINE/'tests'))
from kanidm_passkey import qualifier


if __name__ == '__main__':
    try:
        paquet=os.environ.get('MRJAM_KANIDM');curl=os.environ.get('MRJAM_CURL')
        if not paquet or not curl:raise ValueError('outils natifs verrouillés requis')
        print(json.dumps(qualifier(paquet,curl),sort_keys=True))
    except Exception:
        path=RACINE/'state/kanidm-passkey-diagnostic-private.log'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as out:traceback.print_exc(file=out)
        print('Passkey native non qualifiée ; diagnostic privé conservé.',file=sys.stderr)
        sys.exit(1)
