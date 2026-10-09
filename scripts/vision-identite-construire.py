"""Construire Keycloak sur le socle VPS conservé, sans démarrage ni activation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'
DIAGNOSTIC = None
spec = importlib.util.spec_from_file_location('preparation', ROOT / 'scripts/vision-multiutilisateur-preparer.py')
preparation = importlib.util.module_from_spec(spec); spec.loader.exec_module(preparation)


class ConstructionRefusee(RuntimeError):
    """Uniquement une raison constante, jamais une réponse d'un outil."""


def exiger(condition, raison):
    if not condition: raise ConstructionRefusee(raison)


def etape(nom):
    global ETAPE
    ETAPE = nom
    print(json.dumps({'etape': nom}), flush=True)


def commande(*args, timeout=240):
    try:
        r = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ConstructionRefusee('Délai de construction ou de contrôle dépassé') from None
    if r.returncode:
        preparation.diagnostic_prive(b'\nCommande interrompue ; stderr prive :\n' + r.stderr)
        raise ConstructionRefusee('Commande de construction ou de contrôle refusée')
    return r.stdout.decode()


def dossier_prive(path):
    info = path.lstat()
    exiger(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and
        not info.st_mode & 0o077, 'Dossier de qualification non privé')


def lire_prive(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        exiger(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and
            not info.st_mode & 0o077 and info.st_size < 65536, 'Rapport privé non conforme')
        with os.fdopen(fd) as f:
            fd = None
            return json.load(f)
    finally:
        if fd is not None: os.close(fd)


def preuve_preparation(rapport, preuve, candidat):
    exiger(preuve['vision'] == candidat['vision'] and preuve['style'] == candidat['style'] and
        preuve['source_sha256'] == candidat['source_sha256'], 'Candidat différent de la préparation qualifiée')
    exiger(rapport['version'] == 1 and rapport['infrastructure'] == preuve['infrastructure'] and
        rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        all(rapport[k] is True for k in ('restauration_vision_reelle', 'migrations_sans_perte',
            'retour_acl_owners_rls', 'retour_rejouable')) and rapport['activation'] is False and
        rapport['inscriptions'] is False, 'Préparation réelle absente ou incomplète')


def store(path):
    exiger(isinstance(path, str) and re.fullmatch(r'/nix/store/[0-9a-z]{32}-[A-Za-z0-9._+-]{1,150}', path),
        'Chemin de paquet inattendu')
    return path


def construire(revision):
    global DIAGNOSTIC
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Exécution Actions root identifiée requise')
    os.umask(0o077)
    parent = Path('/root/vision-identite-operations')
    d = parent / revision
    dossier_prive(parent); dossier_prive(d)
    exiger(ROOT == d / 'source', 'Source opérateur différente')
    DIAGNOSTIC = d / 'diagnostic-prive.log'; preparation.DIAGNOSTIC = DIAGNOSTIC
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    preuve = json.loads((ROOT / 'operations/vision-multiutilisateur-qualification.json').read_text())
    audit = candidat['audit']

    def controler():
        exiger(str(Path('/run/current-system').resolve()) == audit['systeme'] and
            str(Path('/nix/var/nix/profiles/system').resolve()) == audit['systeme'], 'Génération différente : nouvel audit requis')
        exiger(str(Path('/srv/vision/current').resolve()) == audit['vision'], 'Release Vision différente : nouvel audit requis')
        exiger(commande('nix-instantiate', '--find-file', 'nixpkgs').strip() == audit['nixpkgs'], 'Nixpkgs installé différent')
        exiger(preparation.socle.source_fournisseur_active() == audit['fournisseur'], 'Fournisseur actif différent : nouvel audit requis')
        configuration = json.loads(commande('nix-instantiate', '--eval', '--strict', '--json',
            ROOT / 'scripts/vision-multiutilisateur-config.nix', '--argstr', 'configuration', '/etc/nixos/configuration.nix',
            '--argstr', 'fournisseur', audit['fournisseur'], '-I', 'nixpkgs=' + audit['nixpkgs']))
        exiger(configuration['systeme'] == audit['systeme'] and configuration['postgres_majeure'] == '17' and
            configuration['postgres_tcp'] is False and configuration['postgres_ecoute'] == '' and
            configuration['fournisseur_source'] == audit['fournisseur'], 'Socle actif non reproduit')

    etape('invariants_actifs'); controler()
    exiger(not (d / 'construction.json').exists(), 'Construction déjà terminée')
    etape('preuve_preparation')
    exiger(re.fullmatch('[0-9a-f]{40}', preuve['infrastructure']), 'Révision de qualification invalide')
    ancien = Path('/root/vision-multiutilisateur-operations') / preuve['infrastructure']
    dossier_prive(ancien.parent); dossier_prive(ancien)
    preuve_preparation(lire_prive(ancien / 'preparation.json'), preuve, candidat)
    exiger(hashlib.sha256((ROOT / 'vendor/vision-multiutilisateur-source.tar.gz').read_bytes()).hexdigest() ==
        candidat['source_sha256'], 'Archive Vision différente')
    disponible = next(int(ligne.split()[1]) for ligne in Path('/proc/meminfo').read_text().splitlines()
        if ligne.startswith('MemAvailable:'))
    exiger(disponible >= 4 * 1024 * 1024, 'Mémoire disponible insuffisante pour cette construction')
    etape('evaluation_paquet')
    expression = ROOT / 'scripts/vision-identite-paquet.nix'
    resume = json.loads(commande('nix-instantiate', '--eval', '--strict', '--json', expression,
        '--attr', 'resume', '-I', 'nixpkgs=' + audit['nixpkgs']))
    exiger(resume['version'] == '26.7.3' and resume['jdbc_unix'] is True and
        resume['preconditions_validees'] is False and resume['inscriptions'] is False and
        resume['activation'] is False and len(resume['plugins']) == 5, 'Paquet ou conditions inattendus')
    store(resume['source']); store(resume['paquet'])
    for plugin in resume['plugins']: store(plugin)
    etape('construction_paquet')
    paquet = commande('nix-build', expression, '--attr', 'paquet', '-I', 'nixpkgs=' + audit['nixpkgs'],
        '--out-link', d / 'paquet', '--max-jobs', '1', '--cores', '2', timeout=1500).strip()
    exiger(paquet == resume['paquet'] and str((d / 'paquet').resolve()) == paquet, 'Paquet construit différent')
    etape('verification_version_plugins')
    version = commande(Path(paquet) / 'bin/kc.sh', '--version', timeout=90)
    exiger(re.search(r'^Keycloak 26\.7\.3\b', version, re.MULTILINE), 'Version construite différente')
    # La racine GC du paquet conserve aussi ses sources/dépendances de runtime.
    # Conserver les entrées de compilation explicitement : elles peuvent être
    # absentes de la fermeture runtime après l'optimisation Quarkus.
    for numero, chemin in enumerate([resume['source'], *resume['plugins']]):
        commande('nix-store', '--add-root', d / ('entree-' + str(numero)), '--realise', chemin)
    providers = sorted(p.name for p in (Path(paquet) / 'providers').glob('*.jar'))
    exiger('mrjam-identite.jar' in providers and len(providers) == 5 and
        any('junixsocket-common' in p for p in providers) and
        any('junixsocket-native-common' in p for p in providers), 'Plugins construits incomplets')
    etape('invariants_finaux'); controler()
    rapport = dict(version=1, infrastructure=revision, preparation=preuve['infrastructure'],
        vision=candidat['vision'], style=candidat['style'], keycloak='26.7.3', paquet=paquet,
        plugins=providers, construction=True, jdbc_unix_configure=True,
        jdbc_unix_vps_qualifie=False, identite_initiale=False, activation=False, inscriptions=False)
    preparation.sauver(d / 'construction.json', rapport)
    print(json.dumps(rapport, ensure_ascii=False), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('revision'); a = p.parse_args()
    try:
        construire(a.revision)
    except Exception as erreur:
        try: preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        rapport = dict(construction='interrompue', etape=ETAPE, activation=False, donnees_affichees=False)
        if isinstance(erreur, ConstructionRefusee): rapport['raison'] = str(erreur)
        print(json.dumps(rapport, ensure_ascii=False), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__': main()
