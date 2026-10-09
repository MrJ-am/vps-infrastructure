"""Préparer et vérifier l'import privé initial, sans importer ni créer de personne.

Les secrets existants ne sont jamais remplacés. Une relance vérifie exactement
le même import ; toute divergence demande une opération coordonnée distincte.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ('oidc-client.secret', 'cycle-client.secret', 'admission-client.secret',
           'fermeture-hook.secret', 'fermeture-client.secret')


def exiger(condition, raison):
    if not condition: raise ValueError(raison)


def ouvrir_prive(rootfd, nom, drapeaux=os.O_RDONLY, maximum=1048576):
    fd = os.open(nom, drapeaux | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=rootfd)
    try:
        info = os.fstat(fd)
        exiger(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and
               stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and
               info.st_size <= maximum, 'Fichier privé non conforme')
        return fd
    except Exception:
        os.close(fd)
        raise


def lire(rootfd, nom, maximum=1048576):
    with os.fdopen(ouvrir_prive(rootfd, nom, maximum=maximum)) as f:
        value = f.read(maximum + 1)
        exiger(len(value.encode()) <= maximum, 'Fichier privé trop volumineux')
        return value


def ecrire(rootfd, nom, valeur):
    fd = ouvrir_prive(rootfd, nom, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, 'w') as f:
        f.write(valeur); f.flush(); os.fsync(f.fileno())
    os.fsync(rootfd)


def config_courriel(chemin):
    source = ROOT / 'services/mrjam-courriel/courriel.py'
    spec = importlib.util.spec_from_file_location('mrjam_courriel', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    path = Path(chemin)
    exiger(path.is_absolute() and path == path.resolve(), 'SMTP privé sans lien requis')
    parentfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: config = module.verifier_smtp(json.loads(lire(parentfd, path.name, 65536)))
    finally: os.close(parentfd)
    return {'host': config['host'], 'port': str(config['port']),
            'from': config['from_address'], 'fromDisplayName': 'MrJ.am',
            'auth': 'true', 'user': config['username'], 'password': config['password'],
            'starttls': 'true', 'ssl': 'false'}


def assembler(modele, valeurs, smtp):
    realm = json.loads(Path(modele).read_text())
    exiger(realm['realm'] == 'mrjam' and realm['registrationAllowed'] is False and
           len(realm['clients']) == 1 and realm['clients'][0]['clientId'] == 'mrjam-vision' and
           not realm.get('users') and not realm.get('smtpServer'), 'Modèle initial inattendu')
    profil = json.loads((ROOT / 'operations/identite/profil.json').read_text())
    realm.setdefault('components', {})['org.keycloak.userprofile.UserProfileProvider'] = [{
        'providerId': 'declarative-user-profile', 'subComponents': {},
        'config': {'kc.user.profile.config': [json.dumps(profil, ensure_ascii=False)]}}]
    if smtp is not None: realm['smtpServer'] = smtp
    realm['clients'][0]['secret'] = valeurs['oidc-client.secret']
    for nom, droits in (('cycle', ['view-users']),
                        ('admission', ['manage-users', 'view-users']),
                        ('fermeture', ['manage-users'])):
        client = 'mrjam-' + nom
        realm['clients'].append({'clientId': client, 'secret': valeurs[nom + '-client.secret'],
            'protocol': 'openid-connect', 'publicClient': False, 'serviceAccountsEnabled': True,
            'standardFlowEnabled': False, 'directAccessGrantsEnabled': False,
            'implicitFlowEnabled': False, 'fullScopeAllowed': False,
            'redirectUris': [], 'webOrigins': []})
        realm.setdefault('users', []).append({'username': 'service-account-' + client,
            'enabled': True, 'serviceAccountClientId': client,
            'clientRoles': {'realm-management': droits}})
        realm.setdefault('clientScopeMappings', {}).setdefault('realm-management', []).append(
            {'client': client, 'roles': droits})
    return realm


def preparer(modele, destination, smtp=None, *, controler=False):
    root = Path(destination)
    exiger(root.is_absolute() and root == root.resolve(), 'Répertoire absolu sans lien requis')
    if not controler: root.mkdir(mode=0o700, parents=True, exist_ok=True)
    rootfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lockfd = None
    try:
        info = os.fstat(rootfd)
        exiger(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
               'Répertoire non privé ou propriétaire différent')
        lockfd = ouvrir_prive(rootfd, '.preparation.lock',
            os.O_RDONLY if controler else os.O_RDWR | os.O_CREAT, maximum=0)
        try: fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Autre préparation en cours') from None
        # Vérifier tous les fichiers existants et le SMTP avant toute génération.
        valeurs = {}
        for nom in SECRETS:
            try: valeur = lire(rootfd, nom, 512)
            except FileNotFoundError:
                exiger(not controler, 'Secret initial absent')
                continue
            exiger(re.fullmatch(r'[A-Za-z0-9_-]{43}', valeur), 'Format de secret invalide')
            valeurs[nom] = valeur
        try:
            existant = json.loads(lire(rootfd, 'mrjam-realm.json'))
            exiger(isinstance(existant, dict), 'Import initial invalide')
        except FileNotFoundError: existant = None
        exiger(existant is None or len(valeurs) == len(SECRETS), 'Import existant incomplet')
        configuration = config_courriel(smtp) if smtp else None
        assembler(modele, {nom: valeurs.get(nom, 'validation') for nom in SECRETS}, configuration)
        if existant is None:
            exiger(not controler, 'Import initial absent')
            for nom in SECRETS:
                if nom not in valeurs:
                    valeurs[nom] = secrets.token_urlsafe(32)
                    ecrire(rootfd, nom, valeurs[nom])
        realm = assembler(modele, valeurs, configuration)
        if existant is None:
            ecrire(rootfd, 'mrjam-realm.json', json.dumps(realm, ensure_ascii=False))
        else:
            exiger(existant == realm, 'Import différent : opération coordonnée requise')
        return {'import_prive_prepare': True, 'import_existant_verifie': existant is not None,
                'inscriptions': False, 'secret_affiche': False, 'smtp_configure': bool(smtp),
                'rotation': False, 'identite_humaine': False}
    finally:
        if lockfd is not None: os.close(lockfd)
        os.close(rootfd)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--modele', required=True); p.add_argument('--destination', required=True)
    p.add_argument('--smtp-prive'); p.add_argument('--controler', action='store_true')
    a = p.parse_args()
    try: print(json.dumps(preparer(a.modele, a.destination, a.smtp_prive, controler=a.controler)))
    except Exception:
        # Les exceptions JSON/SMTP peuvent contenir une valeur privée.
        p.exit(1, 'Préparation privée refusée ; aucun contenu affiché.\n')
