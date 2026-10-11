"""Sélection centrale depuis le diff Git de l'infrastructure (sans sources privées)."""
import json
import os
import re
import subprocess
from assemblage import catalogue,selection

avant=os.environ.get('MRJAM_COMMIT_AVANT','')
if avant and re.fullmatch('[a-f0-9]{40}',avant) and set(avant)!={'0'}:
    fichiers=subprocess.check_output(['git','diff','--name-only',avant,'HEAD'],text=True).splitlines()
    suites=selection(['vps/'+f for f in fichiers],catalogue())
else:suites=sorted(catalogue())
besoin=bool(set(suites)-{'editorial','selection'})
with open(os.environ['GITHUB_OUTPUT'],'a') as f:
    f.write('composants='+str(besoin).lower()+'\n')
print(json.dumps({'suites_concernees':suites,'composants_requis':besoin},ensure_ascii=False))
