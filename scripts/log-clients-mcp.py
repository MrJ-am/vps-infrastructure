"""Reprise des registrations publiques OAuth, jamais des comptes/sessions/jetons.

    L'autorisation reste une nouvelle décision avec session Native vérifiée,
    retour exact et PKCE S256. Le client public n'est pas une identité métier.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit


def exiger(v,message):
    if not v:raise ValueError(message)


def lire_clients(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3) as db:
        clients=list(db.execute('SELECT id,nom,redirections,cree FROM oauth_clients'))
    exiger(len(clients)<=2000,'Registre historique hors limite')
    for identifiant,nom,redirections,created in clients:
        exiger(isinstance(identifiant,str) and re.fullmatch('[A-Za-z0-9_-]{32}',identifiant),'Identifiant client historique inattendu')
        exiger(isinstance(nom,str) and 1<=len(nom)<=100 and all(ord(c)>=32 for c in nom),'Nom client historique inattendu')
        uris=json.loads(redirections)
        exiger(isinstance(uris,list) and 1<=len(uris)<=5,'Retours historiques hors limite')
        for uri in uris:
            exiger(isinstance(uri,str) and 9<=len(uri)<=1024 and all(33<=ord(c)<=126 for c in uri)
                   and '\\' not in uri and '#' not in uri,'Retour historique invalide')
            url=urlsplit(uri)
            exiger(url.scheme=='https' and url.hostname and not url.username and not url.password,
                   'Retour historique non HTTPS ou ambigu')
        exiger(isinstance(created,int) and 0<=created<=9007199254740991,'Date client historique invalide')
    return clients


def reprendre(clients,path):
    """Transaction bornée ; ne remplace jamais un client concurrent différent."""
    with sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=3) as db:
        db.execute('BEGIN IMMEDIATE')
        nouveaux=0;existants=0
        for identifiant,nom,uris,created in clients:
            actuel=db.execute('SELECT name,redirects,created FROM log_oauth_clients WHERE id=?',(identifiant,)).fetchone()
            if actuel:
                exiger(actuel[0]==nom and json.loads(actuel[1])==json.loads(uris) and actuel[2]==created,
                       'Client concurrent différent : aucune écriture retenue')
                existants+=1
            else:
                db.execute('INSERT INTO log_oauth_clients VALUES(?,?,?,?)',(identifiant,nom,uris,created))
                nouveaux+=1
        exiger(db.execute('SELECT count(*) FROM log_oauth_clients').fetchone()[0]<=2048,'Registre actuel hors limite')
    return dict(clients_importes=nouveaux,clients_identiques_conserves=existants,
                comptes_importes=0,sessions_importees=0,jetons_importes=0,
                nouvelle_autorisation_native_requise=True)


def main():
    exiger(os.geteuid()==0,'Opérateur central Root requis')
    import fcntl,pwd,subprocess
    with open('/root/mrjam-log.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        subprocess.run(['systemctl','is-active','mrjam-metier','kanidm'],check=True,stdout=subprocess.DEVNULL)
        clients=lire_clients(Path('/var/lib/mrj-auth/sessions.sqlite'))
        # Aucun WAL/shm créé sous UID Root pour la base active du monolithe.
        user=pwd.getpwnam('mrjam-metier');os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
        print(json.dumps(reprendre(clients,Path('/var/lib/mrjam-metier/log/sessions.sqlite'))))

if __name__=='__main__':main()
