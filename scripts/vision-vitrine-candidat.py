#!/usr/bin/env python3
"""Contrôler les archives figées avant leur transfert administratif.

Le serveur est construit depuis les sources identifiées. L’interface vient de
la CI et ses empreintes couvrent aussi les images et les fontes de l’application.
"""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile


def verifier(racine):
    candidat = json.loads((racine/'operations/vision-vitrine-candidat.json').read_text())
    for cle in ('application','style','audit_revision'):
        assert re.fullmatch('[0-9a-f]{40}',candidat[cle]),'Révision non exacte'
    assert candidat['migrations'] == [],'Cette publication ne migre pas les données'
    assert set(candidat['fichiers']) == {'vendor/vision-vitrine-source.tar.gz','vendor/vision-vitrine-interface.zip'}
    for nom, attendu in candidat['fichiers'].items():
        assert hashlib.sha256((racine/nom).read_bytes()).hexdigest()==attendu,'Archive modifiée : '+nom
    with tarfile.open(racine/'vendor/vision-vitrine-source.tar.gz') as archive:
        membres=archive.getmembers()
        assert all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in membres)
        assert len({m.name for m in membres})==len(membres),'Fichiers source ambigus'
        assert archive.extractfile('revision-application.txt').read().decode().strip()==candidat['application']
        tutoriel=json.load(archive.extractfile('docs/tutoriel.json'))
        assert len(tutoriel['sections'])==11
        assert json.load(archive.extractfile('interface/style.lock.json'))['revision']==candidat['style']
    with zipfile.ZipFile(racine/'vendor/vision-vitrine-interface.zip') as archive:
        manifeste=json.loads(archive.read('manifest.json'))
        assert manifeste['revisionApplication']==candidat['application'] and manifeste['revisionStyle']==candidat['style']
        assert {n for n in archive.namelist() if not n.endswith('/')}==set(manifeste['fichiers'])|{'manifest.json'}
        for nom, attendu in manifeste['fichiers'].items():
            assert not nom.startswith('/') and '..' not in Path(nom).parts
            assert hashlib.sha256(archive.read(nom)).hexdigest()==attendu,'Fichier compilé modifié'
        # Ce namespace est réellement servi par la configuration active : aucun
        # ajout implicite à Nginx n’est nécessaire pour montrer les cinq visuels.
        images=[n for n in manifeste['fichiers'] if n.startswith('assets/mrjam/vision/')]
        assert len(images)==5 and sum(len(archive.read(n)) for n in images)<200000
    return candidat


if __name__=='__main__':
    verifier(Path(__file__).resolve().parents[1])
    print('Archives exactes, tutoriel et cinq visuels contrôlés. Aucune activation.')
