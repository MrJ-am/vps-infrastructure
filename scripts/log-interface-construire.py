"""Assemblage local Log, socle et Signature exacts ; aucune publication."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from assemblage import RACINE, chemins_sources, manifeste
from frontends import cache_style, contenus, sha


def construire():
    m=manifeste();sources=chemins_sources();edge=m['frontends_infrastructure']['log']
    for nom,revision in [('style',edge['revision_style']),('signature',edge['revision_signature'])]:
        actuel=subprocess.check_output(['git','rev-parse','HEAD'],cwd=sources[nom],text=True).strip()
        if actuel!=revision or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=sources[nom]):
            raise ValueError('Producteur Log différent de sa révision verrouillée : '+nom)
    commun=cache_style(sources['style'],edge['revision_style'])
    site=RACINE/'interface-log/dist';site.mkdir(parents=True,exist_ok=True)
    dependency=RACINE/'interface-log/.dependances/style-mrjam'
    if dependency.exists():shutil.rmtree(dependency) # cache dérivé de ce seul consommateur
    dependency.mkdir(parents=True);shutil.copytree(commun/'src',dependency/'src')
    env=dict(os.environ,ELM_HOME=str(RACINE/'state/elm-home'))
    subprocess.run(['python3',str(RACINE/'scripts/revoir-frontends.py'),'--composant','log'],env=env,check=True)
    exe=sources['matheval']/'docs/node_modules/.bin/elm'
    subprocess.run([str(exe),'make','src/Main.elm','--optimize','--output=dist/elm.js'],cwd=RACINE/'interface-log',env=env,check=True)
    for p in ('index.html','pont.js'):shutil.copyfile(RACINE/'interface-log'/p,site/p)
    assets=site/'assets/mrjam';assets.mkdir(parents=True,exist_ok=True)
    for p in ('signature.css','MrJamSignature.woff2','EchoPoint.woff2'):shutil.copyfile(sources['signature']/'web'/p,assets/p)
    shutil.copyfile(sources['signature']/'artwork/Echologo.svg',assets/'Echologo.svg')
    shutil.copyfile(commun/'public/assets/mrjam/animations.js',assets/'animations.js')
    h=contenus(site);rapport={'format':1,'sources':{'application':contenus(RACINE/'interface-log/src'),
        'bootstrap':sha((RACINE/'interface-log/index.html').read_bytes()),'interop':sha((RACINE/'interface-log/pont.js').read_bytes()),
        'elm_json':sha((RACINE/'interface-log/elm.json').read_bytes()),'style':edge['revision_style'],'signature':edge['revision_signature']},
        'fichiers':h,'ensemble_sha256':sha(json.dumps(h,sort_keys=True).encode()),'publication':False}
    (RACINE/'state/log-interface-construction.json').write_text(json.dumps(rapport,indent=2)+'\n')
    print(json.dumps({'ensemble_sha256':rapport['ensemble_sha256'],'fichiers':len(h),'publication':False}))
    return site


if __name__=='__main__':construire()
