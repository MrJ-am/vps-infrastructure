"""Vérifier les deux artefacts testés avant toute publication coordonnée."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from logique_artefact import exiger
from registry import unique_object


def lire(source, projet, reference, repertoire="candidats"):
    archive = source / 'vendor' / repertoire / (projet + '.zip')
    exiger(hashlib.sha256(archive.read_bytes()).hexdigest() == reference['sha256'], 'Archive différente : ' + projet)
    fichiers = {}
    with zipfile.ZipFile(archive) as paquet:
        exiger(sum(p.file_size for p in paquet.infolist()) <= 64*1024*1024, 'Archive trop grande')
        noms = set()
        for entree in paquet.infolist():
            nom = entree.filename
            chemin = PurePosixPath(nom)
            exiger(nom not in noms and not chemin.is_absolute() and '..' not in chemin.parts
                   and '\\' not in nom and str(chemin) == nom.rstrip('/')
                   and stat.S_IFMT(entree.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR), 'Entrée ZIP invalide')
            noms.add(nom)
            if entree.is_dir(): continue
            if projet == 'logique':
                exiger(nom.startswith('dist/'), 'Préfixe Logique absent')
                nom = nom[5:]
            exiger(not any(p.startswith('.') for p in PurePosixPath(nom).parts), 'Fichier caché interdit')
            fichiers[nom] = paquet.read(entree)
    nom = 'manifeste-preparation.json' if projet == 'logique' else 'manifest.json'
    manifeste = json.loads(fichiers[nom], object_pairs_hook=unique_object)
    cles = ('application','style','signature','empreintes') if projet == 'logique' else ('revisionApplication','revisionStyle','revisionSignature','fichiers')
    for cle, attendu in zip(cles[:3], (reference['application'], reference['style'], reference['signature'])):
        exiger(re.fullmatch('[0-9a-f]{40}', attendu) and manifeste[cle] == attendu, 'Révision incohérente : '+cle)
    empreintes = manifeste[cles[3]]
    exiger(set(fichiers) == set(empreintes) | {nom}, 'Inventaire incomplet')
    for chemin, attendu in empreintes.items():
        exiger(hashlib.sha256(fichiers[chemin]).hexdigest() == attendu, 'Fichier altéré : '+chemin)
    for police, attendu in {
        'MrJamSignature.woff2':'1525a85c58cdea88dcb93e077c4da98d2af1ff70ae7e6710fdeda36e8af28604',
        'EchoPoint.woff2':'816109c8291b12a0b2a8f0f981cc260a074a55190d94df322b57196755caebda',
    }.items():
        exiger(empreintes.get('assets/mrjam/'+police) == attendu, 'Police originale absente')
    if projet == 'logique':
        exiger(manifeste['portageComplet'] is True and manifeste['typographieValidee'] is True, 'Validation typographique absente')
    return manifeste, fichiers


def verifier(source):
    references = json.loads((source/'operations/corrections-artefacts.json').read_text())
    exiger(references['logique']['style'] == references['vision']['style'] == references['matheval']['style'], 'Styles différents')
    for projet in ('logique','vision','matheval'):
        reference = references[projet]
        exiger(reference['ci']['conclusion'] == 'success'
               and type(reference['ci']['execution']) is int
               and reference['ci']['revision'] == reference['application'], 'Preuve CI exacte absente')
    return {p: lire(source,p,references[p]) for p in ('logique','vision')}


if __name__ == '__main__':
    import sys
    source = Path(__file__).resolve().parents[1]
    resultat = verifier(source)
    if len(sys.argv) == 2:
        cible = Path(sys.argv[1]); cible.mkdir(parents=True, exist_ok=False)
        for projet, (_, fichiers) in resultat.items():
            for nom, contenu in fichiers.items():
                p = cible/projet/nom;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(contenu)
    print('Deux artefacts intègres, trois consommateurs validés, même style figé.')

