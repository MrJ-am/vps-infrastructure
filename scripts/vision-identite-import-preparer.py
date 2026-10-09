"""Préparer le seul import initial privé après qualification Unix réelle."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = Path('/var/lib/mrjam-identite')
ETAPE = 'demarrage'


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


unix = charger('qualification_unix', 'vision-identite-unix-qualifier.py')
identite = charger('preparer_identite', 'identite-preparer.py')
construction = unix.construction
exiger = construction.exiger


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape': nom}), flush=True)


def preuve_unix(rapport, preuve, candidat, build):
    techniques = ('demarrage_optimise', 'version_native', 'spi_charge',
        'inscription_native_fermee', 'api_synthetique', 'jdbc_unix_vps_qualifie',
        'peer_sans_mot_de_passe', 'autre_uid_refuse', 'dynamic_user', 'reseau_prive',
        'postgresql_tcp_ferme', 'runtimes_retires')
    cles = ('version', 'infrastructure', 'construction', 'vision', 'style', 'keycloak',
            'paquet', *techniques, 'identite_initiale', 'activation', 'inscriptions')
    exiger(set(rapport) == set(cles) and all(rapport.get(k) == preuve[k] for k in cles),
           'Qualification Unix privée différente ou incomplète')
    exiger(rapport['version'] == 1 and rapport['keycloak'] == '26.7.3' and
        all(rapport[k] is True for k in techniques) and
        all(rapport[k] is False for k in ('identite_initiale', 'activation', 'inscriptions')) and
        rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        rapport['construction'] == build['infrastructure'] and rapport['paquet'] == build['paquet'],
        'Qualification Unix ou candidat inattendu')


def preparer(revision, controler=False):
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision),
           'Exécution Actions root identifiée requise')
    os.umask(0o077)
    d = Path('/root/vision-identite-import-operations') / revision
    construction.dossier_prive(d.parent); construction.dossier_prive(d)
    exiger(ROOT == d / 'source', 'Source opérateur différente')
    construction.preparation.DIAGNOSTIC = d / 'diagnostic-prive.log'
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    etape('invariants_actifs'); construction.verifier_socle(candidat)
    if controler:
        print(json.dumps({'socle_inchange': True, 'activation': False, 'inscriptions': False}))
        return
    etape('preuves_privees')
    build = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())
    preuve = json.loads((ROOT / 'operations/vision-identite-unix-qualification.json').read_text())
    for p in (build, preuve):
        exiger(re.fullmatch('[0-9a-f]{40}', p['infrastructure']), 'Révision de preuve invalide')
    ancien = Path('/root/vision-identite-operations') / build['infrastructure']
    construction.dossier_prive(ancien.parent); construction.dossier_prive(ancien)
    resume = json.loads(construction.commande('nix-instantiate', '--eval', '--strict', '--json',
        ROOT / 'scripts/vision-identite-paquet.nix', '--attr', 'resume',
        '-I', 'nixpkgs=' + candidat['audit']['nixpkgs']))
    unix.preuve_construction(construction.lire_prive(ancien / 'construction.json'), build, candidat, resume)
    ancien = Path('/root/vision-identite-unix-operations') / preuve['infrastructure']
    construction.dossier_prive(ancien.parent); construction.dossier_prive(ancien)
    preuve_unix(construction.lire_prive(ancien / 'qualification.json'), preuve, candidat, build)
    etape('preparation_privee')
    modele = ROOT / 'operations/identite/realm.json'
    smtp = DESTINATION / 'proton-smtp.json'
    resultat = identite.preparer(modele, DESTINATION, smtp)
    etape('verification_import')
    verifie = identite.preparer(modele, DESTINATION, smtp, controler=True)
    exiger(verifie['import_existant_verifie'] is True and verifie['smtp_configure'] is True,
           'Import privé non vérifié')
    etape('invariants_finaux'); construction.verifier_socle(candidat)
    rapport = dict(version=1, infrastructure=revision, construction=build['infrastructure'],
        qualification_unix=preuve['infrastructure'], vision=candidat['vision'], style=candidat['style'],
        keycloak=build['keycloak'], paquet=build['paquet'], import_prive_prepare=True,
        import_verifie=True, import_deja_present=resultat['import_existant_verifie'],
        fichiers_prives=True, secrets_clients=len(identite.SECRETS), rotation=False,
        smtp_configure=True, smtp_contacte=False, identite_humaine=False,
        import_en_base=False, activation=False, inscriptions=False)
    cible = d / 'import.json'
    if cible.exists():
        ancien_rapport = construction.lire_prive(cible)
        exiger({k: v for k, v in ancien_rapport.items() if k != 'import_deja_present'} ==
               {k: v for k, v in rapport.items() if k != 'import_deja_present'},
               'Rapport existant différent')
    else: construction.preparation.sauver(cible, rapport)
    print(json.dumps(rapport), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('revision'); p.add_argument('--controler', action='store_true'); a = p.parse_args()
    try: preparer(a.revision, a.controler)
    except Exception:
        try: construction.preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        # Aucun message d'exception JSON/SMTP ni contenu de fichier n'est public.
        print(json.dumps({'import_prive': 'interrompu', 'etape': ETAPE,
            'activation': False, 'donnees_affichees': False}), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__': main()
