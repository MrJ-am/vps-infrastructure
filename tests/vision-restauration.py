"""Qualifier age, pg_restore et le rejeu d'une demande sur une base jetable.

Usage dans le cluster synthétique seulement : --vision /chemin/source-vision.
Ne télécharge aucune branche et n'utilise jamais les données de production.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vision',required=True);a=p.parse_args()
if os.environ.get('PGHOST')!='127.0.0.1' or os.environ.get('PGUSER')!='postgres':raise SystemExit('Cluster jetable loopback requis')
nom='vision_restauration_'+uuid.uuid4().hex[:12];source=nom+'_source';vision=Path(a.vision).resolve()
def commande(*args,**kw):return subprocess.run(args,check=True,**kw)
def sql(base,texte):return subprocess.check_output(['psql','-XAt','--set=ON_ERROR_STOP=1','--dbname='+base,'--command='+texte],text=True).strip()
try:
    commande('createdb',source)
    sql(source,'CREATE EXTENSION vector')
    commande('sh','scripts/migrate.sh',cwd=vision,env={**os.environ,'PGDATABASE':source},stdout=subprocess.DEVNULL)
    u='test-restauration-'+uuid.uuid4().hex[:12]
    sql(source,f"INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('{u}','Synthétique'); INSERT INTO vision_profils(utilisateur) VALUES('{u}'); INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('{u}','Synthétique','Donnée de test');")
    with tempfile.TemporaryDirectory() as root:
        r=Path(root);cle=r/'cle.age';dump=r/'dump.age';clair=r/'restauration.dump';registre=r/'registre.jsonl'
        commande('age-keygen','-o',str(cle),stderr=subprocess.DEVNULL)
        recipient=subprocess.check_output(['age-keygen','-y',str(cle)],text=True).strip()
        with open(dump,'wb') as f:
            pg=subprocess.Popen(['pg_dump','--format=custom',source],stdout=subprocess.PIPE)
            commande('age','-r',recipient,stdin=pg.stdout,stdout=f);pg.stdout.close();assert pg.wait()==0
        # L'effacement postérieur à la sauvegarde doit survivre à sa restauration.
        registre.write_text(json.dumps({'utilisateur':u,'confirmee_a':1})+'\n');registre.chmod(0o600)
        sql(source,f"SELECT set_config('vision.utilisateur','{u}',false); SELECT vision_gestion.effacer('{u}','EFFACER VISION');")
        commande('age','--decrypt','-i',str(cle),'-o',str(clair),str(dump))
        commande('createdb',nom)
        commande('pg_restore','--exit-on-error','--no-owner','--dbname='+nom,str(clair),stdout=subprocess.DEVNULL)
        # Un dump no-owner doit rétablir les owners de fonctions avant le rejeu.
        commande('psql','-X','--set=ON_ERROR_STOP=1','--dbname='+nom,'--file='+str(vision/'scripts/roles.sql'),stdout=subprocess.DEVNULL)
        assert sql(nom,f"SELECT count(*) FROM vision_fiches WHERE utilisateur='{u}'")=='1'
        commande('python3',str(Path(__file__).resolve().parents[1]/'scripts/vision-effacements-rejouer.py'),'--registre',str(registre),'--base',nom)
        assert sql(nom,f"SELECT count(*) FROM vision_fiches WHERE utilisateur='{u}'")=='0'
        assert sql(nom,f"SELECT count(*) FROM vision_gestion.comptes WHERE utilisateur='{u}'")=='0'
        assert sql(nom,f"SELECT count(*) FROM vision_gestion.effacements WHERE utilisateur='{u}'")=='1'
    print(json.dumps({'age_restaure':True,'pg17_restaure':True,'effacement_non_reintroduit':True}))
finally:
    for base in (nom,source):subprocess.run(['dropdb','--if-exists',base],check=True)
