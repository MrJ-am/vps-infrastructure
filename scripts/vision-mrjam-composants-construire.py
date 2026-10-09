"""Construire les composants sans génération, activation ni lancement de service."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


initial = charger('import_initial', 'vision-identite-import-preparer.py')
verification = charger('composants', 'vision-mrjam-verifier.py')
construction = initial.construction
exiger = construction.exiger


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape': nom}), flush=True)


def preuve_import(rapport, preuve, candidat, unix, build):
    cles = ('version', 'infrastructure', 'construction', 'qualification_unix', 'vision', 'style',
        'keycloak', 'paquet', 'import_prive_prepare', 'import_verifie', 'import_deja_present',
        'fichiers_prives', 'secrets_clients', 'rotation', 'smtp_configure', 'smtp_contacte',
        'identite_humaine', 'import_en_base', 'activation', 'inscriptions')
    exiger(set(rapport) == set(cles) and all(rapport.get(k) == preuve[k] for k in cles),
           'Import privé différent ou incomplet')
    exiger(rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        rapport['construction'] == build['infrastructure'] and
        rapport['qualification_unix'] == unix['infrastructure'] and rapport['paquet'] == build['paquet'] and
        rapport['version'] == 1 and rapport['keycloak'] == '26.7.3' and rapport['secrets_clients'] == 5 and
        all(rapport[k] is True for k in ('import_prive_prepare', 'import_verifie', 'fichiers_prives', 'smtp_configure')) and
        all(rapport[k] is False for k in ('rotation', 'smtp_contacte', 'identite_humaine', 'import_en_base',
            'activation', 'inscriptions')), 'Import privé ou candidat inattendu')


def rapport_prive(prefixe, preuve, nom):
    exiger(re.fullmatch('[0-9a-f]{40}', preuve['infrastructure']), 'Révision de preuve invalide')
    d = Path('/root') / prefixe / preuve['infrastructure']
    construction.dossier_prive(d.parent); construction.dossier_prive(d)
    return construction.lire_prive(d / nom)


def construire(revision, controler=False):
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision),
           'Exécution Actions root identifiée requise')
    os.umask(0o077)
    d = Path('/root/vision-mrjam-composants-operations') / revision
    construction.dossier_prive(d.parent); construction.dossier_prive(d)
    exiger(ROOT == d / 'source', 'Source opérateur différente')
    construction.preparation.DIAGNOSTIC = d / 'diagnostic-prive.log'
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    etape('invariants_actifs'); construction.verifier_socle(candidat)
    if controler:
        print(json.dumps({'socle_inchange': True, 'activation': False, 'inscriptions': False})); return
    exiger(not (d / 'composants.json').exists(), 'Construction déjà terminée')
    etape('preuves_privees')
    def public(nom): return json.loads((ROOT / 'operations' / nom).read_text())
    build = public('vision-identite-construction.json')
    unix = public('vision-identite-unix-qualification.json')
    preuve = public('vision-identite-import-qualification.json')
    r_build = rapport_prive('vision-identite-operations', build, 'construction.json')
    r_unix = rapport_prive('vision-identite-unix-operations', unix, 'qualification.json')
    r_import = rapport_prive('vision-identite-import-operations', preuve, 'import.json')
    initial.preuve_unix(r_unix, unix, candidat, build)
    preuve_import(r_import, preuve, candidat, unix, build)
    initial.identite.preparer(ROOT / 'operations/identite/realm.json', initial.DESTINATION,
        initial.DESTINATION / 'proton-smtp.json', controler=True)
    etape('evaluation_composants')
    args = [ROOT / 'scripts/vision-mrjam-composants.nix',
        '--argstr', 'fournisseur', candidat['audit']['fournisseur'],
        '-I', 'nixpkgs=' + candidat['audit']['nixpkgs']]
    resume = json.loads(construction.commande('nix-instantiate', '--eval', '--strict', '--json',
        *args, '--attr', 'resume'))
    verification.verifier_resume(resume)
    exiger(resume['fournisseur_source'] == candidat['audit']['fournisseur'], 'Fournisseur candidat différent')
    initial.unix.preuve_construction(r_build, build, candidat,
        dict(version=resume['keycloak_version'], paquet=resume['keycloak'], jdbc_unix=resume['jdbc_unix'],
             preconditions_validees=resume['preconditions_validees'],
             inscriptions=resume['inscriptions'], activation=resume['activation']))
    etape('construction_lot')
    lot = construction.commande('nix-build', *args, '--attr', 'lot', '--out-link', d / 'lot',
        '--max-jobs', '1', '--cores', '2', timeout=1200).strip()
    exiger(lot == resume['lot'] and str((d / 'lot').resolve()) == lot, 'Lot construit différent')
    etape('imports_natifs')
    controles = verification.verifier(resume, commande=lambda a: construction.commande(*a, timeout=60))
    etape('sources_agpl')
    construction.commande(sys.executable, ROOT / 'tests/sources-mrjam.py',
        Path(resume['sources']) / 'services-mrjam.tar.gz')
    etape('invariants_finaux'); construction.verifier_socle(candidat)
    rapport = dict(version=1, infrastructure=revision, import_prive=preuve['infrastructure'],
        vision=candidat['vision'], style=candidat['style'], keycloak='26.7.3', paquet=resume['keycloak'],
        lot=lot, sources=resume['sources'], construction=True, sources_agpl=True, garde_activation=True,
        **controles, inscriptions=False, identite_humaine=False)
    construction.preparation.sauver(d / 'composants.json', rapport)
    print(json.dumps(rapport), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('revision'); p.add_argument('--controler', action='store_true'); a = p.parse_args()
    try: construire(a.revision, a.controler)
    except Exception:
        try: construction.preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        print(json.dumps({'composants': 'interrompus', 'etape': ETAPE,
            'activation': False, 'donnees_affichees': False}), file=sys.stderr, flush=True)
        sys.exit(1)
