"""Rejouer le registre durable sur une restauration isolée, avant réouverture.

Aucun contenu n'est écrit ou imprimé. L'effacement confirmé prime après une
panne ayant empêché la réponse HTTP. Ne jamais réattribuer un ancien identifiant.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

def rejouer(registre,base):
    if not re.fullmatch(r'vision_restauration_[a-z0-9_]{1,40}',base):
        raise ValueError('La cible doit être une restauration isolée vision_restauration_*.')
    utilisateurs=set()
    for ligne in Path(registre).read_text().splitlines():
        demande=json.loads(ligne);u=demande['utilisateur']
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',u):raise ValueError('Identifiant invalide')
        utilisateurs.add(u)
    # Les valeurs ne peuvent contenir de quote après validation. Ne jamais
    # afficher les identifiants, le registre ou la sortie détaillée de psql.
    sql='BEGIN;\n'
    for u in sorted(utilisateurs):
        sql+=f"SELECT set_config('vision.utilisateur','{u}',true);\nDO $$ BEGIN IF EXISTS(SELECT FROM vision_gestion.comptes WHERE utilisateur='{u}') THEN PERFORM vision_gestion.effacer('{u}','EFFACER VISION'); END IF; END $$;\n"
    sql+='COMMIT;\n'
    subprocess.run(['psql','-X','--set=ON_ERROR_STOP=1','--dbname='+base],input=sql,text=True,stdout=subprocess.DEVNULL,check=True)
    return len(utilisateurs)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registre',required=True);p.add_argument('--base',required=True);a=p.parse_args()
    n=rejouer(a.registre,a.base);print(json.dumps({'registre_rejoue':True,'demandes_distinctes':n,'base_isolee':True}))
