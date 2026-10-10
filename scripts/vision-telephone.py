"""Témoin non personnel pour la clé publique reçue du téléphone, sans rotation."""
from email.message import EmailMessage
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

RACINE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('courriel_telephone', RACINE/'services/mrjam-courriel/courriel.py')
courriel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(courriel)
RECIPIENT = 'age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc'
REFERENCE = 'vision-telephone-20261010'
PIECE = 'vision-test-telephone-20261010.json.age'
GENERATION = '/nix/store/k4q4i4m9r4070xwwpnd24hpi9g6zngyn-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
RAPPORT = dict(reference=REFERENCE, accepte_par_relais=True, courrier_chiffre=True,
    presence_en_boite='a_verifier', dechiffrement='a_verifier', sauvegarde_reelle=False,
    rotation_production=False, generation_active_modifiee=False)


def repertoire(chemin):
    chemin.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = chemin.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError('Répertoire privé requis')


def ecrire(chemin, contenu):
    fd = os.open(chemin, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as fichier:
        fichier.write(contenu)
        fichier.flush()
        os.fsync(fichier.fileno())
    fd = os.open(chemin.parent, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def message(config, chiffre):
    m = EmailMessage()
    m['From'] = config['from_address']
    m['To'] = config['from_address']
    m['Subject'] = 'Vision — nouveau test chiffré pour votre téléphone — 10 octobre 2026'
    m.set_content('Ce nouveau témoin utilise la clé publique créée sur votre téléphone le 10 octobre 2026.\n'
        'Ouvrez uniquement la pièce vision-test-telephone-20261010.json.age avec cette nouvelle clé.\n'
        'Elle contient un test sans donnée personnelle, pas une sauvegarde. Ne partagez jamais votre clé privée.\n'
        'Les anciennes copies nécessitent leur ancienne clé et restent conservées.\n')
    m.add_attachment(chiffre, maintype='application', subtype='octet-stream', filename=PIECE)
    return m


def envoyer(root, destination, executable='age'):
    repertoire(root)
    accepte = root/'accepte.json'
    if accepte.exists() or accepte.is_symlink():
        if courriel.lire_prive(accepte) != RAPPORT:
            raise ValueError('Reçu divergent')
        return dict(RAPPORT, deja_transmis=True)
    # Une remise ambiguë exige un diagnostic ; aucun nouvel envoi automatique.
    intention = root/'intention.json'
    if intention.exists() or intention.is_symlink():
        raise ValueError('Remise précédente non établie')
    config = courriel.verifier_smtp(courriel.lire_prive(destination/'proton-smtp.json'))
    if config['from_address'].casefold() != 'automath@mrj.am':
        raise ValueError('Boîte existante requise')
    contenu = json.dumps(dict(qualification_telephone=True, reference=REFERENCE,
        cle_publique_sha256=hashlib.sha256(RECIPIENT.encode()).hexdigest()), sort_keys=True).encode()
    chiffre = subprocess.run([executable, '-r', RECIPIENT], input=contenu,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=10).stdout
    if not chiffre.startswith(b'age-encryption.org/v1\n') or len(chiffre) > 4096:
        raise ValueError('Cryptogramme invalide')
    ecrire(root/PIECE, chiffre)
    ecrire(intention, json.dumps(dict(reference=REFERENCE, recipient=RECIPIENT,
        chiffre_sha256=hashlib.sha256(chiffre).hexdigest())).encode())
    courriel.transmettre(config, message(config, chiffre))
    ecrire(accepte, json.dumps(RAPPORT).encode())
    return dict(RAPPORT, deja_transmis=False)


def verifier_socle():
    if str(Path('/run/current-system').resolve()) != GENERATION or str(Path('/nix/var/nix/profiles/system').resolve()) != GENERATION:
        raise ValueError('Socle différent')


def main():
    if len(sys.argv) != 2 or not re.fullmatch('[0-9a-f]{40}', sys.argv[1]) or os.geteuid() != 0:
        raise ValueError('Opérateur root exact requis')
    revision = sys.argv[1]
    root = Path('/root/vision-telephone-operations')/revision
    if RACINE != root/'source':
        raise ValueError('Source exacte requise')
    os.umask(0o077)
    repertoire(root)
    fd = os.open(root/'verrou', os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        verifier_socle()
        rapport = envoyer(root/'transmission', Path('/var/lib/mrjam-identite'))
        verifier_socle()
        print(json.dumps(rapport))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Les réponses SMTP peuvent contenir des adresses ou un détail privé.
        print('Témoin du téléphone refusé ; diagnostic privé requis, aucun secret affiché.', file=sys.stderr)
        sys.exit(1)
