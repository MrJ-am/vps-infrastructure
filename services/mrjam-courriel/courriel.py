"""Courriels transactionnels privés, file durable et TLS obligatoire.

L'accusé SMTP signifie « accepté par le relais », pas « lu ou reçu en boîte ».
Un envoi interrompu après DATA peut être rejoué : le Message-ID reste stable.
Ce module ne fournit aucune route publique d'envoi de courrier.
"""
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
import fcntl
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import ssl
import stat
import struct
import subprocess
import time


def acl_lecture_individuelle(acl,uid):
    # systemd260 ajoute ACL_READ au seul uid du service. Le masque ACL rend
    # st_mode=0440 sans accorder de lecture au groupe propriétaire.
    if len(acl)!=44 or struct.unpack('<I',acl[:4])[0]!=2:return False
    attendu=[(1,4,0xffffffff),(2,4,uid),(4,0,0xffffffff),
        (16,4,0xffffffff),(32,0,0xffffffff)]
    return [struct.unpack('<HHI',acl[n:n+8]) for n in range(4,len(acl),8)]==attendu


def ouvrir_prive(chemin,maximum=65536):
    fd=os.open(chemin,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>maximum or s.st_uid not in (0,os.geteuid()):
            raise ValueError('Fichier de secret non privé')
        try:acl=os.getxattr(fd,'system.posix_acl_access')
        except OSError as erreur:
            if erreur.errno not in (errno.ENODATA,errno.ENOTSUP):raise
            acl=None
        if acl is None:
            prive=not s.st_mode&0o077
        else:
            prive=stat.S_IMODE(s.st_mode)==0o440 and acl_lecture_individuelle(acl,os.geteuid())
        if not prive:raise ValueError('Fichier de secret non privé')
        return fd
    except Exception:
        os.close(fd);raise


def lire_secret_prive(chemin):
    with os.fdopen(ouvrir_prive(chemin,128)) as f:valeur=f.read(128).strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',valeur):raise ValueError('secret_invalide')
    return valeur


def lire_prive(chemin):
    fd = ouvrir_prive(chemin)
    try:
        with os.fdopen(fd, 'r') as fichier:
            fd = None
            return json.load(fichier)
    finally:
        if fd is not None:
            os.close(fd)


def verifier_smtp(config):
    requis = {'host', 'port', 'username', 'password', 'from_address',
              'starttls_required', 'certificate_verification'}
    if set(config) != requis or config['host'] != 'smtp.protonmail.ch' or config['port'] != 587:
        raise ValueError('Configuration Proton SMTP invalide')
    if config['starttls_required'] is not True or config['certificate_verification'] is not True:
        raise ValueError('TLS et vérification du certificat obligatoires')
    if not re.fullmatch(r'[A-Za-z0-9]{16,128}', config['password']):
        raise ValueError('Jeton SMTP invalide')
    adresse(config['username'])
    adresse(config['from_address'])
    if config['username'].casefold() != config['from_address'].casefold():
        raise ValueError('Adresse active du jeton requise')
    return config


def adresse(valeur):
    if not isinstance(valeur, str) or len(valeur) > 254 or not re.fullmatch(
            r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', valeur):
        raise ValueError('Adresse de courrier invalide')
    return valeur


def transmettre(config, message):
    # Pas de fallback en clair, pas d'authentification avant STARTTLS.
    with smtplib.SMTP(config['host'], config['port'], timeout=20) as relais:
        relais.ehlo()
        relais.starttls(context=ssl.create_default_context())
        relais.ehlo()
        relais.login(config['username'], config['password'])
        refus = relais.send_message(message)
        if refus:
            raise smtplib.SMTPRecipientsRefused(refus)


class FileCourriel:
    def __init__(self, chemin, expediteur, transport=transmettre):
        self.chemin = Path(chemin)
        self.expediteur = adresse(expediteur)
        self.transport = transport
        root = self.chemin.parent
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077 or self.chemin.is_symlink():
            raise ValueError('File de courrier non privée')
        with self.ouvrir() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS courriels (
                cle TEXT PRIMARY KEY, message BLOB NOT NULL, cree INTEGER NOT NULL,
                etat TEXT NOT NULL DEFAULT 'attente', essais INTEGER NOT NULL DEFAULT 0,
                prochain INTEGER NOT NULL DEFAULT 0, accepte INTEGER, erreur TEXT)''')
            if 'empreinte' not in {r[1] for r in db.execute('PRAGMA table_info(courriels)')}:
                db.execute('ALTER TABLE courriels ADD COLUMN empreinte TEXT')
            for cle, contenu in db.execute('SELECT cle,message FROM courriels WHERE empreinte IS NULL').fetchall():
                db.execute('UPDATE courriels SET empreinte=? WHERE cle=?', (hashlib.sha256(contenu).hexdigest(), cle))

    def ouvrir(self):
        db = sqlite3.connect(self.chemin, timeout=30)
        os.chmod(self.chemin, 0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA journal_mode=DELETE')
        return db

    def ajouter(self, cle, destinataire, sujet, texte, piece=None):
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', cle):
            raise ValueError('Clé de déduplication invalide')
        if not isinstance(sujet, str) or len(sujet) > 160 or any(ord(c) < 32 for c in sujet):
            raise ValueError('Sujet invalide')
        if not isinstance(texte, str) or len(texte.encode()) > 16000:
            raise ValueError('Message trop long')
        message = EmailMessage(policy=SMTP)
        message['From'] = self.expediteur
        message['To'] = adresse(destinataire)
        message['Subject'] = sujet
        message['Message-ID'] = '<' + hashlib.sha256(cle.encode()).hexdigest() + '@mrj.am>'
        message.set_content(texte)
        if piece is not None:
            if not isinstance(piece, bytes) or len(piece) > 65536:
                raise ValueError('Pièce chiffrée trop grande')
            message.add_attachment(piece, maintype='application', subtype='octet-stream',
                                   filename='effacement.json.age')
        with self.ouvrir() as db:
            # Même clé : ne jamais modifier le destinataire ou un message déjà envoyé.
            ancien = db.execute('SELECT empreinte,cree FROM courriels WHERE cle=?', (cle,)).fetchone()
            cree = ancien[1] if ancien else int(time.time())
            message['Date'] = formatdate(cree, usegmt=True)
            # Les frontières MIME sont aléatoires : comparer le contenu métier séparément
            # via un identifiant déterministe de frontière.
            if piece is not None:
                message.set_boundary('mrjam-' + hashlib.sha256(cle.encode()).hexdigest())
            contenu = message.as_bytes()
            empreinte = hashlib.sha256(contenu).hexdigest()
            if ancien and ancien[0] != empreinte:
                raise ValueError('Clé déjà utilisée pour un autre message')
            db.execute('INSERT OR IGNORE INTO courriels(cle,message,cree,empreinte) VALUES(?,?,?,?)',
                       (cle, contenu, cree, empreinte))
        self.synchroniser_repertoire()
        return self.etat(cle)

    def synchroniser_repertoire(self):
        fd = os.open(self.chemin.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def etat(self, cle):
        with self.ouvrir() as db:
            ligne = db.execute('SELECT etat,essais,accepte,erreur FROM courriels WHERE cle=?', (cle,)).fetchone()
        return dict(zip(('etat', 'essais', 'accepte_a', 'erreur'), ligne)) if ligne else None

    def annuler(self, cle):
        with self.ouvrir() as db:
            db.execute("UPDATE courriels SET etat='annule' WHERE cle=? AND etat='attente'", (cle,))

    def purger(self, maintenant=None):
        maintenant = int(time.time()) if maintenant is None else maintenant
        with self.ouvrir() as db:
            # Supprimer les adresses, corps et pièces locales après trente jours.
            # L'état minimal empêche les rejeux après panne ; le registre externe
            # reste soumis à la durée des copies qu'il protège.
            db.execute("UPDATE courriels SET message=X'' WHERE (etat='accepte_relais' AND accepte<?) OR (etat='annule' AND cree<?)",
                       (maintenant - 30 * 86400, maintenant - 30 * 86400))

    def traiter(self, config, maintenant=None, cle=None):
        from email.parser import BytesParser
        verifier_smtp(config)
        maintenant = int(time.time()) if maintenant is None else maintenant
        fd = os.open(str(self.chemin) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with self.ouvrir() as db:
                lignes = db.execute("SELECT cle,message,essais FROM courriels WHERE etat='attente' AND prochain<=? AND (? IS NULL OR cle=?) ORDER BY cree LIMIT 20", (maintenant, cle, cle)).fetchall()
            for cle, contenu, essais in lignes:
                erreur = None
                try:
                    self.transport(config, BytesParser(policy=SMTP).parsebytes(contenu))
                except (OSError, smtplib.SMTPException):
                    # Ne jamais stocker le texte du relais : il peut contenir adresse ou secret.
                    erreur = 'relais_indisponible'
                with self.ouvrir() as db:
                    if erreur:
                        db.execute('UPDATE courriels SET essais=essais+1,erreur=?,prochain=? WHERE cle=?',
                                   (erreur, maintenant + min(3600, 60 * 2 ** min(essais, 6)), cle))
                    else:
                        db.execute("UPDATE courriels SET etat='accepte_relais',essais=essais+1,accepte=?,erreur=NULL WHERE cle=?", (maintenant, cle))
            return len(lignes)
        finally:
            os.close(fd)


def chiffrer_effacement(utilisateur, date, recipient, executable='age'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', utilisateur) or type(date) is not int or date <= 0:
        raise ValueError('Intention d’effacement invalide')
    if not re.fullmatch(r'age1[0-9a-z]{58}', recipient):
        raise ValueError('Destinataire age invalide')
    donnees = json.dumps({'version': 1, 'utilisateur': utilisateur, 'confirmee_a': date}, separators=(',', ':')).encode()
    return subprocess.run([executable, '-r', recipient], input=donnees, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=10, check=True).stdout


def archiver_effacement(file, utilisateur, date, recipient_age, adresse_exploitant, executable='age'):
    cle = 'effacement:' + hashlib.sha256(f'{utilisateur}:{date}'.encode()).hexdigest()
    ancien = file.etat(cle)
    if ancien:
        return ancien
    piece = chiffrer_effacement(utilisateur, date, recipient_age, executable)
    # Aucun identifiant d'usager dans le sujet ou le texte du courriel.
    return file.ajouter(cle, adresse_exploitant, 'MrJ.am — registre chiffré d’effacement',
                       'Une intention d’effacement est jointe, chiffrée pour la clé de restauration.\n'
                       'Conserver cette pièce pour appliquer les effacements avant toute réouverture après restauration.', piece)


if __name__ == '__main__':
    os.umask(0o077)
    config = verifier_smtp(lire_prive(os.environ['MRJ_SMTP_SECRET']))
    file = FileCourriel(os.environ['MRJ_COURRIEL_FILE'], config['from_address'])
    file.traiter(config)
    file.purger()
