"""Préparer ou vérifier le snapshot déjà retenu par Vision, sans changer le modèle.

Le téléchargement est une opération explicite de qualification. Le fournisseur
de production et le chargement ASDF ne téléchargent rien.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from assemblage import RACINE, chemins_sources


def verifier(dossier):
    verrou=json.loads((RACINE/'assemblage/modele-vision.json').read_text())
    dossier=Path(dossier)
    if dossier.is_symlink() or not dossier.is_dir():raise ValueError('Snapshot absent ou lien interdit')
    attendus={f['chemin']:f['sha256'] for f in verrou['fichiers']}
    obtenus={}
    for p in sorted(dossier.rglob('*')):
        if '.cache' in p.relative_to(dossier).parts:continue
        if p.is_symlink():raise ValueError('Lien interdit dans le snapshot')
        if p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as f:
                for bloc in iter(lambda:f.read(1024*1024),b''):h.update(bloc)
            obtenus[str(p.relative_to(dossier))]=h.hexdigest()
    if obtenus!=attendus:raise ValueError('Snapshot différent de la révision et des empreintes verrouillées')
    return {'modele':verrou['modele'],'revision':verrou['revision'],'fichiers':obtenus}


def chemin():
    verrou=json.loads((RACINE/'assemblage/modele-vision.json').read_text())
    return RACINE/'state/modeles-qualifications'/verrou['revision']/'.modele-test'


def preparer():
    cible=chemin()
    if cible.exists():return verifier(cible)
    parent=cible.parent
    parent.mkdir(parents=True,exist_ok=True)
    if parent.is_symlink() or not parent.resolve().is_relative_to(RACINE/'state/modeles-qualifications'):
        raise ValueError('Cache modèle extérieur')
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL')}
    env.update(HF_HUB_DISABLE_TELEMETRY='1',VISION_MODELE_REVISION=parent.name)
    with tempfile.TemporaryDirectory(prefix='snapshot-',dir=parent) as tmp:
        subprocess.run([RACINE/'state/outils-python/embeddings/bin/python',sources['vision']/'tests/telecharger_modele.py'],
                       cwd=tmp,env=env,timeout=600,check=True)
        rapport=verifier(Path(tmp)/'.modele-test')
        # Le répertoire caché de téléchargement n'est pas une entrée du modèle.
        shutil.rmtree(Path(tmp)/'.modele-test/.cache',ignore_errors=True)
        if cible.exists():return verifier(cible) # auteur concurrent : préserver
        os.rename(Path(tmp)/'.modele-test',cible)
    return rapport


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preparer',action='store_true')
    a=p.parse_args();rapport=preparer() if a.preparer else verifier(chemin())
    print(json.dumps({'revision':rapport['revision'],'modele':rapport['modele'],
        'nombre_fichiers':len(rapport['fichiers']),
        'ensemble_sha256':hashlib.sha256(json.dumps(rapport['fichiers'],sort_keys=True).encode()).hexdigest()}))
