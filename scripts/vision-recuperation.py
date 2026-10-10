"""Copies testées puis chiffrées pour le téléphone ; jamais de clé privée reçue."""
from email.message import EmailMessage
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import subprocess
import tarfile

RECIPIENT = 'age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc'
REFERENCE = 'vision-recuperation-20261010'
PIECE = 'vision-recuperation-20261010.tar.gz.age'
VERIFICATEUR = 'verifier-vision-recuperation.py'
MAXIMUM_COURRIEL = 15000000
REGISTRES = {'effacements.jsonl':'/var/lib/vision-effacements/demandes.jsonl',
    'effacements-cycle.jsonl':'/var/lib/vision-cycle/effacements.jsonl',
    'effacements-communs.jsonl':'/var/lib/mrjam-fermeture/effacements.jsonl'}


def empreinte(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for bloc in iter(lambda:f.read(1024*1024),b''): h.update(bloc)
    return h.hexdigest()


def verifier_confirmation(path):
    d = json.loads(Path(path).read_text())
    if type(d.get('version')) is not int or d['version'] != 1 or d.get('execution') != 38047719442 or d.get('reference') != 'vision-telephone-20261010' or d.get('cle_publique') != RECIPIENT or d.get('cle_publique_sha256') != hashlib.sha256(RECIPIENT.encode()).hexdigest() or d.get('reception_confirmee_par_exploitant') is not True or d.get('dechiffrement_temoin_confirme_par_exploitant') is not True or d.get('cle_privee_transmise') is not False:
        raise ValueError('Confirmation du téléphone requise')


def copier_prive(source,cible,maximum):
    fd = os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as entree:
        s = os.fstat(entree.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_mode & 0o007 or s.st_size > maximum:
            raise ValueError('Source privée invalide')
        contenu = entree.read(maximum+1)
        apres = os.fstat(entree.fileno())
        if len(contenu) != s.st_size or (s.st_size,s.st_mtime_ns) != (apres.st_size,apres.st_mtime_ns):
            raise ValueError('Source privée modifiée')
    with cible.open('xb') as f:
        f.write(contenu); f.flush(); os.fsync(f.fileno())
    cible.chmod(0o600)


def copier_sessions(source,cible):
    s = source.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_mode & 0o007 or s.st_nlink != 1:
        raise ValueError('Sessions privées requises')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as entree, sqlite3.connect(cible) as sortie:
        entree.execute('PRAGMA query_only=ON'); entree.backup(sortie)
        if sortie.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('Copie SQLite invalide')
    cible.chmod(0o600)


def archiver(fichiers,cible,age='age',recipient=RECIPIENT):
    descriptions = {}
    for nom,path in fichiers.items():
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_mode & 0o077 or s.st_nlink != 1:
            raise ValueError('Fichier de copie non privé')
        descriptions[nom] = dict(taille=s.st_size,sha256=empreinte(path))
    if sum(x['taille'] for x in descriptions.values()) > 512*1024*1024:
        raise ValueError('Jeu de copies trop grand')
    preuve = secrets.token_hex(32)
    manifest = dict(version=1,reference=REFERENCE,cle_publique_sha256=hashlib.sha256(RECIPIENT.encode()).hexdigest(),
        fichiers=descriptions,preuve=preuve,bases_restaurees=True,sqlite_integrite=True,
        sauvegarde_vps_complete=False,registre_externe_recent_requis=True)
    fd = os.open(cible,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as sortie:
        p = subprocess.Popen([str(age),'-r',recipient],stdin=subprocess.PIPE,stdout=sortie,stderr=subprocess.DEVNULL)
        try:
            with tarfile.open(fileobj=p.stdin,mode='w|gz',format=tarfile.USTAR_FORMAT) as archive:
                contenu = json.dumps(manifest).encode()
                info = tarfile.TarInfo('manifest.json'); info.size = len(contenu); info.mode = 0o600
                archive.addfile(info,io.BytesIO(contenu))
                for nom,path in sorted(fichiers.items()):
                    info = tarfile.TarInfo(nom); info.size = descriptions[nom]['taille']; info.mode = 0o600
                    with path.open('rb') as entree: archive.addfile(info,entree)
            p.stdin.close()
            if p.wait(timeout=120) != 0: raise ValueError('Chiffrement refusé')
            sortie.flush(); os.fsync(sortie.fileno())
        finally:
            if p.poll() is None: p.kill(); p.wait(timeout=10)
    taille = cible.stat().st_size
    if not 0 < taille <= MAXIMUM_COURRIEL: raise ValueError('Limite de courrier dépassée')
    return dict(chiffre_sha256=empreinte(cible),chiffre_octets=taille,
        preuve_sha256=hashlib.sha256(preuve.encode()).hexdigest())


def preparer(d,isole,root,config,age,revision):
    copier_sessions(Path('/var/lib/mrj-auth/sessions.sqlite'),isole/'sessions.sqlite')
    copier_prive('/var/lib/vision/auth/htpasswd',isole/'auth.htpasswd',16384)
    copier_prive(d/'acl-avant.json',isole/'acl.json',1048576)
    contexte = dict(version=1,infrastructure=revision,systeme=config['systeme'],postgres_paquet=config['postgres_paquet'],
        portee='donnees-et-acces-vision-identite-avant-bascule',migrations_vision=18,
        identite_socket='/run/mrjam-amorcage-postgresql',sauvegarde_vps_complete=False,
        registre_externe_recent_requis=True)
    with (isole/'contexte.json').open('x') as f: json.dump(contexte,f)
    (isole/'contexte.json').chmod(0o600)
    fichiers = {nom:isole/nom for nom in ('vision.dump','identite.dump','sessions.sqlite','auth.htpasswd','acl.json','contexte.json')}
    for nom,path in REGISTRES.items():
        if Path(path).exists() or Path(path).is_symlink():
            copier_prive(path,isole/nom,8*1024*1024); fichiers[nom] = isole/nom
    receipt = archiver(fichiers,d/PIECE,age)
    return dict(version=1,infrastructure=revision,reference=REFERENCE,piece=PIECE,**receipt,
        verificateur_sha256=empreinte(root/'scripts'/VERIFICATEUR),cle_publique=RECIPIENT,
        restauration_vision_reelle=True,restauration_identite_reelle=True,sqlite_integrite=True,
        cle_temoin_confirmee_par_exploitant=True,copie_exterieure_verifiee=False,
        sauvegarde_vps_complete=False,registre_externe_recent_requis=True,
        generation_active_modifiee=False,configuration_sauvegardes_modifiee=False,
        activation=False,inscriptions=False)


def transmettre(d,root,rapport):
    spec = importlib.util.spec_from_file_location('courriel_recuperation',root/'services/mrjam-courriel/courriel.py')
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    config = c.verifier_smtp(c.lire_prive('/var/lib/mrjam-identite/proton-smtp.json'))
    if config['from_address'].casefold() != 'automath@mrj.am' or empreinte(d/PIECE) != rapport['chiffre_sha256'] or empreinte(root/'scripts'/VERIFICATEUR) != rapport['verificateur_sha256']:
        raise ValueError('Copie ou boîte différente')
    intention = d/'remise-intention.json'
    if intention.exists() or intention.is_symlink(): raise ValueError('Remise ambiguë : aucun rejeu')
    message = EmailMessage()
    message['From'] = config['from_address']; message['To'] = config['from_address']
    message['Subject'] = 'Vision — copie de récupération chiffrée pour votre téléphone — 10 octobre 2026'
    message.set_content('Copie privée des bases Vision et identité, des sessions et des éléments de reprise de l’accès actuel.\n'
        'Les deux bases ont été restaurées et comparées sur le serveur, dans un cluster isolé sans TCP.\n'
        'Enregistrez les deux pièces jointes dans Documents ; le vérificateur contrôlera le fichier complet sans écrire son contenu en clair.\n'
        'Cette copie ne couvre pas le VPS entier. Elle ne remplace pas la copie mensuelle sur disque Linux ni le registre récent des effacements.\n')
    message.add_attachment((d/PIECE).read_bytes(),maintype='application',subtype='octet-stream',filename=PIECE)
    message.add_attachment((root/'scripts'/VERIFICATEUR).read_bytes(),maintype='application',subtype='octet-stream',filename=VERIFICATEUR)
    fd = os.open(intention,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(rapport,f); f.flush(); os.fsync(f.fileno())
    fd = os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
    c.transmettre(config,message)
    rapport['accepte_par_relais'] = True
