"""Copie chiffrée du seul cluster privé arrêté ; aucune restauration implicite."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess

DONNEES=Path('/var/lib/mrjam-amorcage-postgresql')

def empreinte(fd):
    os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();taille=0
    while bloc:=os.read(fd,1048576):h.update(bloc);taille+=len(bloc)
    return dict(taille=taille,sha256=h.hexdigest())


def copier(fd, tar, age, destinataire, verifier, diagnostic):
    verifier()
    # Une sauvegarde qui omettrait un tablespace ou WAL externe est refusée.
    for repertoire, dossiers, fichiers in os.walk(DONNEES, followlinks=False):
        for nom in dossiers+fichiers:
            p=Path(repertoire)/nom;s=p.lstat()
            if not (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)):
                raise ValueError('Objet externe ou spécial dans le cluster privé')
    out=os.fdopen(os.dup(fd),'wb')
    # Stderr reste dans des pipes privés, jamais transmis au journal public.
    a=t=None
    try:
        t=subprocess.Popen([tar,'--numeric-owner','--one-file-system','--format=pax',
            '--acls','--xattrs','-cf','-','-C','/var/lib','--',DONNEES.name],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        a=subprocess.Popen([age,'-r',destinataire],stdin=t.stdout,stdout=out,stderr=subprocess.PIPE)
        t.stdout.close()
        t.stdout=None
        _,erreur_age=a.communicate(timeout=120)
        _,erreur_tar=t.communicate(timeout=10)
        if a.returncode or t.returncode:
            diagnostic(erreur_age+erreur_tar)
            raise ValueError('Copie privée chiffrée refusée')
        out.flush();os.fsync(out.fileno())
        verifier()
        os.lseek(fd,0,os.SEEK_SET)
        if os.read(fd,22)!=b'age-encryption.org/v1\n':
            raise ValueError('Copie privée non chiffrée')
        return dict(chiffree=True,**empreinte(fd),
            cluster_arrete_avant_apres=True,restauration_reelle=False)
    finally:
        for p in (a,t):
            if p is not None and p.poll() is None:p.kill();p.wait()
        if t is not None:
            if t.stdout:t.stdout.close()
            if t.stderr:t.stderr.close()
        if a is not None and a.stderr:a.stderr.close()
        out.close()
