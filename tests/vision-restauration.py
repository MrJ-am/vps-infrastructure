"""Qualifier age, pg_restore et le rejeu d'une demande sur une base jetable.

Usage dans le cluster synthétique seulement : --vision /chemin/source-vision.
Ne télécharge aucune branche et n'utilise jamais les données de production.
"""
import argparse
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import urllib.request
import urllib.parse

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vision',required=True);p.add_argument('--identite-port',type=int);a=p.parse_args()
if os.environ.get('PGHOST')!='127.0.0.1' or os.environ.get('PGUSER')!='postgres':raise SystemExit('Cluster jetable loopback requis')
nom='vision_restauration_'+uuid.uuid4().hex[:12];source=nom+'_source';vision=Path(a.vision).resolve()
realm=None;admin=None
def api(path,donnees=None,methode=None):
    headers={'Authorization':'Bearer '+admin} if admin else {}
    corps=None
    if donnees is not None:corps=json.dumps(donnees).encode();headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(a.identite_port)+path,corps,headers,method=methode),timeout=20) as r:
        contenu=r.read();return json.loads(contenu) if contenu else None
def commande(*args,**kw):return subprocess.run(args,check=True,**kw)
def sql(base,texte):return subprocess.check_output(['psql','-XAt','--set=ON_ERROR_STOP=1','--dbname='+base,'--command='+texte],text=True).strip()
try:
    commande('createdb',source)
    sql(source,'CREATE EXTENSION vector')
    commande('sh','scripts/migrate.sh',cwd=vision,env={**os.environ,'PGDATABASE':source},stdout=subprocess.DEVNULL)
    u='test-restauration-'+uuid.uuid4().hex[:12]
    sql(source,f"INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('{u}','Synthétique'); INSERT INTO vision_profils(utilisateur) VALUES('{u}'); INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('{u}','Synthétique','Donnée de test');")
    sujet=str(uuid.uuid4());u2='test-fermeture-'+uuid.uuid4().hex[:12]
    if a.identite_port:
        assert 38000<=a.identite_port<39000
        corps=urllib.parse.urlencode({'client_id':'admin-cli','username':'qualification','password':'uniquement-test-local','grant_type':'password'}).encode()
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(a.identite_port)+'/realms/master/protocol/openid-connect/token',corps),timeout=20) as r:admin=json.load(r)['access_token']
        realm='qualification-restauration-'+uuid.uuid4().hex[:12]
        modele={'realm':realm,'enabled':True,'users':[{'id':sujet,'username':'synthetique','enabled':True,'email':'synthetique@example.test','emailVerified':True}]}
        api('/admin/realms',modele)
        assert api('/admin/realms/'+realm+'/users/'+sujet)['id']==sujet
        sql(source,f"INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('{u2}','Synthétique'); INSERT INTO vision_profils(utilisateur) VALUES('{u2}'); INSERT INTO vision_gestion.identites VALUES('https://compte.mrj.am/realms/mrjam','{sujet}','{u2}'); INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('{u2}','Privé','À effacer après restauration');")
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
        arguments=['--registre',str(registre),'--base',nom]
        if realm:
            global_registre=r/'global.jsonl';config=r/'identite.json';chiffre=r/'global.age'
            global_registre.write_text(json.dumps({'version':2,'type':'fermeture_commune','emetteur':'https://compte.mrj.am/realms/mrjam',
                'sujet':sujet,'confirmee_a':1,'outils':{'vision':[u2]}})+'\n');global_registre.chmod(0o600)
            commande('age','-r',recipient,'-o',str(chiffre),str(global_registre))
            global_registre.unlink();commande('age','-d','-i',str(cle),'-o',str(global_registre),str(chiffre));global_registre.chmod(0o600)
            config.write_text(json.dumps({'version':1,'base_isolee':'http://127.0.0.1:'+str(a.identite_port),'realm':realm,'utilisateur':'qualification','mot_de_passe':'uniquement-test-local'}));config.chmod(0o600)
            arguments+=['--registre',str(global_registre),'--identite-config',str(config)]
        commande('python3',str(Path(__file__).resolve().parents[1]/'scripts/vision-effacements-rejouer.py'),*arguments)
        assert sql(nom,f"SELECT count(*) FROM vision_fiches WHERE utilisateur='{u}'")=='0'
        assert sql(nom,f"SELECT count(*) FROM vision_gestion.comptes WHERE utilisateur='{u}'")=='0'
        assert sql(nom,f"SELECT count(*) FROM vision_gestion.effacements WHERE utilisateur='{u}'")=='1'
        if realm:
            assert sql(nom,f"SELECT count(*) FROM vision_fiches WHERE utilisateur='{u2}'")=='0'
            assert api('/admin/realms/'+realm+'/users')==[]
            commande('python3',str(Path(__file__).resolve().parents[1]/'scripts/vision-effacements-rejouer.py'),*arguments)
    print(json.dumps({'age_restaure':True,'pg17_restaure':True,'effacement_non_reintroduit':True,'fermeture_commune_rejouee':bool(realm)}))
finally:
    if realm:api('/admin/realms/'+realm,methode='DELETE')
    for base in (nom,source):subprocess.run(['dropdb','--if-exists',base],check=True)
