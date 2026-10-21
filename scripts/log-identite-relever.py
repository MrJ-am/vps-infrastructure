"""Relever le nom et le mail du propriétaire, seulement sous forme chiffrée.

Canal SSH central existant. Ni récupération d'un compte administrateur, ni
lecture de credential Kanidm, ni écriture dans une base ou une configuration.
La clé privée de déchiffrement reste dans l'atelier de l'acteur.
"""
import base64
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile


def relever(plan, base):
    """Croiser le plan d'activation avec le rattachement actuel en lecture seule."""
    sujet = plan.get('subject')
    nom = plan.get('name')
    mail = plan.get('mail')
    if not (isinstance(sujet, str) and re.fullmatch('[a-f0-9-]{36}', sujet)
            and isinstance(nom, str) and re.fullmatch('[A-Za-z0-9_.-]{1,64}', nom)
            and isinstance(mail, str) and 3 <= len(mail) <= 320
            and '@' in mail and not any(ord(c) < 32 or ord(c) == 127 for c in mail)):
        raise ValueError('Métadonnées du propriétaire invalides')
    with sqlite3.connect(base.resolve().as_uri() + '?mode=ro', uri=True, timeout=3) as db:
        db.execute('PRAGMA query_only=ON')
        lignes = db.execute('SELECT mail FROM log_principaux WHERE subject=?', (sujet,)).fetchall()
    if lignes != [(mail.lower(),)]:
        raise ValueError('Rattachement actuel différent du plan')
    return {'identifiant': nom, 'mail': lignes[0][0]}


def chiffrer(document, destinataire):
    public = base64.b64decode(destinataire, validate=True)
    if not (public.startswith(b'-----BEGIN PUBLIC KEY-----\n') and len(public) <= 1024):
        raise ValueError('Format de clé publique invalide')
    donnees = json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode()
    # RSA4096/OAEP-SHA256 : 512 - 2*32 - 2 octets maximum.
    if len(donnees) > 446:
        raise ValueError('Relevé hors borne de chiffrement')
    with tempfile.TemporaryDirectory(prefix='log-identite-public-') as tmp:
        cle = Path(tmp) / 'public.pem'
        cle.write_bytes(public)
        verification = subprocess.run(['openssl', 'pkey', '-pubin', '-in', str(cle),
            '-text_pub', '-noout'], capture_output=True, timeout=10)
        if verification.returncode or not verification.stdout.startswith(b'Public-Key: (4096 bit)'):
            raise ValueError('Clé RSA4096 requise')
        resultat = subprocess.run(['openssl', 'pkeyutl', '-encrypt', '-pubin', '-inkey', str(cle),
            '-pkeyopt', 'rsa_padding_mode:oaep', '-pkeyopt', 'rsa_oaep_md:sha256'],
            input=donnees, capture_output=True, timeout=10)
    if resultat.returncode or len(resultat.stdout) != 512:
        raise ValueError('Chiffrement du relevé refusé')
    return base64.b64encode(resultat.stdout).decode('ascii')


def main(revision, destinataire):
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Révision invalide')
    plan = Path('/root/mrjam-assemblages') / revision / 'activation-log-privee.json'
    document = relever(json.loads(plan.read_text()), Path('/var/lib/mrjam-metier/log/sessions.sqlite'))
    print(json.dumps({'format': 1, 'lecture_seule': True, 'algorithme': 'RSA4096-OAEP-SHA256',
                      'identite_chiffree': chiffrer(document, destinataire)}))


if __name__ == '__main__':
    try:
        main(sys.argv[1], DESTINATAIRE)
    except Exception:
        # Aucun message d'exception/plan/SQL/adresse dans les journaux publics.
        print('Relevé privé refusé ; aucune identité publiée.', file=sys.stderr)
        sys.exit(1)
