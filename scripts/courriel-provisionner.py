"""Installer Proton hors store depuis Actions ; aucun démarrage ou changement DNS.

Le jeton arrive sur stdin. Une valeur existante différente bloque l'opération :
la rotation constitue une opération séparée. Le test est envoyé à l'expéditeur
déjà reçu dans la boîte du propriétaire, jamais à une adresse de tiers.
"""
import argparse
from email.message import EmailMessage
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

RACINE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('courriel_prive', RACINE / 'services/mrjam-courriel/courriel.py')
courriel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(courriel)


def synchroniser(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def installer(destination, jeton):
    if not isinstance(jeton, str) or not re.fullmatch(r'[A-Za-z0-9]{16,128}', jeton):
        raise ValueError('Jeton invalide')
    root = Path(destination)
    if not root.is_absolute():
        raise ValueError('Destination absolue requise')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError('Destination non privée')
    config = courriel.verifier_smtp(dict(host='smtp.protonmail.ch', port=587,
        username='automath@mrj.am', from_address='automath@mrj.am', password=jeton,
        starttls_required=True, certificate_verification=True))
    cible = root / 'proton-smtp.json'
    if cible.exists() or cible.is_symlink():
        if courriel.lire_prive(cible) != config:
            raise ValueError('Une rotation explicite est nécessaire')
        return {'installation': 'deja_presente', 'secret_affiche': False}
    fd = os.open(cible, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as fichier:
            json.dump(config, fichier, separators=(',', ':'))
            fichier.flush()
            os.fsync(fichier.fileno())
        synchroniser(root)
    except Exception:
        cible.unlink(missing_ok=True)
        raise
    return {'installation': 'privee', 'secret_affiche': False}


def qualifier(destination, recipient, executable='age'):
    if not re.fullmatch(r'age1[0-9a-z]{58}', recipient):
        raise ValueError('Clé publique age invalide')
    config = courriel.verifier_smtp(courriel.lire_prive(Path(destination) / 'proton-smtp.json'))
    # Ce témoin ne désigne aucun usager et n'est pas un registre d'effacement.
    contenu = json.dumps({'qualification_smtp': True, 'date': int(time.time())}).encode()
    piece = subprocess.run([executable, '-r', recipient], input=contenu,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=10).stdout
    message = EmailMessage()
    message['From'] = config['from_address']
    message['To'] = config['from_address']
    message['Subject'] = 'MrJ.am — qualification du courrier chiffré'
    message.set_content('Test technique de la transmission privée. La pièce jointe chiffrée ne contient aucune donnée d’usager.\n'
        'Ce test ne constitue pas un registre d’effacement. Sa présence en boîte et son déchiffrement doivent être vérifiés.\n')
    message.add_attachment(piece, maintype='application', subtype='octet-stream', filename='qualification-smtp.json.age')
    courriel.transmettre(config, message)
    return {'tls_et_authentification': True, 'courrier_chiffre': True,
        'accepte_par_relais': True, 'presence_en_boite': 'a_verifier', 'dechiffrement': 'a_verifier'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', default='/var/lib/mrjam-identite')
    p.add_argument('--tester', action='store_true')
    p.add_argument('--recipient-age')
    a = p.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Installation root par Actions requise')
    os.umask(0o077)
    # Lecture bornée ; ni mot de passe Proton, ni JSON libre, ni adresse de tiers.
    jeton = sys.stdin.read(130).strip()
    rapport = installer(a.destination, jeton)
    if a.tester:
        rapport.update(qualifier(a.destination, a.recipient_age or ''))
    print(json.dumps(rapport, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Les exceptions SMTP peuvent contenir des adresses et des réponses privées.
        print('Provisionnement ou qualification du courrier refusé ; aucun secret affiché.', file=sys.stderr)
        sys.exit(1)
