"""Sauvegarder puis restaurer les trois bases dans un cluster Unix privé.

Exclusivement via la CI centrale existante. Aucune écriture SQL, interruption ou
restauration sur la production. Clé de transition age éphémère enveloppée pour
le destinataire personnel déjà configuré ; jamais transmise au serveur métier.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid

GENERATION='/nix/store/r6s7ags3dir21gxph8y32rpk8w6lghsb-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
BASES=('vision','matheval','mrjam_identite')
ETAPE='preconditions'

def exiger(v):
    if not v:raise ValueError('Précondition ou qualification refusée')

def commande(args,*,input=None,output=subprocess.PIPE,timeout=60):
    # Aucun stderr de SQL/restore, ni contenu privé, dans les journaux.
    r=subprocess.run([str(a) for a in args],input=input,stdout=output,
                     stderr=subprocess.DEVNULL,timeout=timeout)
    exiger(r.returncode==0);return r.stdout

def repertoire(path):
    p=Path(path);p.mkdir(mode=0o700,exist_ok=True)
    s=p.lstat();exiger(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o077);return p

def identifiant(s):return '"'+s.replace('"','""')+'"'

def services():
    return {n:commande(['systemctl','show',n,'--property=MainPID','--value']).decode().strip()
            for n in ('nginx','postgresql','vision','matheval','mrj-auth','keycloak','vision-embeddings','phpfpm-nextcloud')}

def nix(expression):
    return json.loads(commande(['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json','--expr',expression]))

def schema(requete):
    tables=json.loads(requete("SELECT coalesce(json_agg(json_build_array(schemaname,tablename) ORDER BY schemaname,tablename),'[]')::text FROM pg_tables WHERE schemaname IN ('public','vision_gestion')"))
    resultat={}
    for namespace,t in tables:
        # SHA-256 PostgreSQL officiel ; seule l'empreinte quitte le serveur SQL.
        q=("SELECT encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') FROM "
           "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') h FROM "
           +identifiant(namespace)+'.'+identifiant(t)+" t) d")
        valeur=requete(q);exiger(re.fullmatch('[0-9a-f]{64}',valeur));resultat[namespace+'.'+t]=valeur
    return resultat

def sql(bin,socket,base,query):
    return commande(['runuser','-u','postgres','--',bin/'psql','-XAtq','--set=ON_ERROR_STOP=1',
                     '--host='+str(socket),'--dbname='+base,'--file=-'],
                     input=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n"+query+';\n').encode()).decode().strip()

def dump_snapshot(bin,base,path,socket='/run/postgresql'):
    p=subprocess.Popen(['runuser','-u','postgres','--',str(bin/'psql'),'-XAtq','--set=ON_ERROR_STOP=1',
                        '--host='+str(socket),'--dbname='+base],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    def requete(q):
        p.stdin.write(q+';\n');p.stdin.flush()
        with_timeout=p.stdout.readline().strip();exiger(bool(with_timeout));return with_timeout
    try:
        p.stdin.write("SET TIME ZONE 'UTC'; SET DateStyle='ISO'; SET statement_timeout='15s'; SET lock_timeout='5s'; BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n");p.stdin.flush()
        snapshot=requete('SELECT pg_export_snapshot()');exiger(re.fullmatch('[0-9A-F-]{1,64}',snapshot))
        avant=schema(requete)
        with path.open('xb') as f:
            commande(['runuser','-u','postgres','--',bin/'pg_dump','--format=custom','--snapshot='+snapshot,
                      '--host='+str(socket),'--lock-wait-timeout=5000',base],output=f,timeout=60);f.flush();os.fsync(f.fileno())
        return avant
    finally:
        if p.poll() is None:
            try:p.stdin.write('ROLLBACK;\n');p.stdin.flush()
            finally:p.stdin.close()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        p.stdout.close()

def sqlite_empreinte(c):
    h=hashlib.sha256()
    for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        h.update(table.encode())
        lignes=[]
        for row in c.execute('SELECT * FROM '+identifiant(table)):
            # Blobs préservés byte pour byte, pas réencodage des messages MIME.
            lignes.append(json.dumps([{'blob':v.hex()} if isinstance(v,bytes) else v for v in row],ensure_ascii=False,separators=(',',':')))
        for row in sorted(lignes):h.update(row.encode());h.update(b'\n')
    return h.hexdigest()

def copie_sqlite(source,cible):
    s=source.lstat();exiger(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not s.st_mode&0o007)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(cible) as copie:
        original.execute('PRAGMA query_only=ON');original.execute('BEGIN')
        avant=sqlite_empreinte(original);original.backup(copie)
        exiger(copie.execute('PRAGMA integrity_check').fetchone()==('ok',) and sqlite_empreinte(copie)==avant)
    cible.chmod(0o600)

def copie_registre(source,cible):
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        avant=os.fstat(f.fileno());exiger(stat.S_ISREG(avant.st_mode) and avant.st_nlink==1 and not avant.st_mode&0o007)
        contenu=f.read(10*1024*1024+1);apres=os.fstat(f.fileno())
        exiger(len(contenu)<=10*1024*1024 and (avant.st_size,avant.st_mtime_ns)==(apres.st_size,apres.st_mtime_ns))
    for ligne in contenu.decode('utf-8').splitlines():exiger(isinstance(json.loads(ligne),dict))
    with cible.open('xb') as f:f.write(contenu);f.flush();os.fsync(f.fileno())

def main(revision):
    global ETAPE
    exiger(os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',revision))
    os.umask(0o077)
    exiger(str(Path('/run/current-system').resolve())==GENERATION and str(Path('/nix/var/nix/profiles/system').resolve())==GENERATION)
    exiger(commande(['nix-instantiate','--find-file','nixpkgs']).decode().strip()==NIXPKGS)
    avant_services=services()
    config="(import <nixpkgs/nixos/lib/eval-config.nix> { system=\"x86_64-linux\"; modules=[ /etc/nixos/configuration.nix ]; }).config"
    configuration=nix('let c='+config+'; in { postgres=c.services.postgresql.finalPackage.outPath; recipient=c.services.vision.backupRecipient; }')
    age=Path(nix('(import <nixpkgs> { system="x86_64-linux"; }).age.outPath'))/'bin'
    bin=Path(configuration['postgres'])/'bin';recipient=configuration['recipient']
    exiger(re.fullmatch('age1[0-9a-z]{58}',recipient) and (age/'age').is_file() and (bin/'postgres').is_file())
    exiger(b' 17.' in commande([bin/'postgres','--version']))
    tag=revision[:12]+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    destination=repertoire('/var/backup/mrjam-transitions')/tag;destination.mkdir(mode=0o700)
    postgres=pwd.getpwnam('postgres')
    isole=Path('/var/lib/postgresql')/('mrjam-restauration-'+tag)
    isole.mkdir(mode=0o700);os.chown(isole,postgres.pw_uid,postgres.pw_gid)
    actif=False
    try:
        with tempfile.TemporaryDirectory(prefix='mrjam-transition-',dir='/root') as tmp:
            tmp=Path(tmp);cle=tmp/'transition.key'
            ETAPE='cle-ephemere'
            commande([age/'age-keygen','--output',cle]);public=commande([age/'age-keygen','-y',cle]).decode().strip()
            commande([age/'age','-r',recipient,'-o',destination/'recuperation-cle.age',cle])
            empreintes={};fichiers={}
            def proteger(source,nom):
                cible=destination/(nom+'.age');commande([age/'age','-r',public,'-o',cible,source])
                restored=tmp/('dechiffre-'+nom)
                commande([age/'age','--decrypt','-i',cle,'-o',restored,cible])
                exiger(hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(restored.read_bytes()).digest())
                fichiers[cible.name]=hashlib.sha256(cible.read_bytes()).hexdigest();return restored
            ETAPE='controle-isole-synthetique'
            commande(['runuser','-u','postgres','--',bin/'initdb','-D',isole/'data','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
            commande(['runuser','-u','postgres','--',bin/'pg_ctl','-D',isole/'data','-l',isole/'serveur.log','-w','-t','20','-o',
                      "-c listen_addresses='' -c unix_socket_directories="+str(isole)+" -c log_min_error_statement=panic -c log_min_messages=fatal",'start']);actif=True
            exiger(sql(bin,isole,'postgres',"SELECT current_setting('listen_addresses')='' AND current_setting('server_encoding')='UTF8'")=='t')
            sql(bin,isole,'postgres','CREATE DATABASE qualification_synthetique')
            sql(bin,isole,'qualification_synthetique',"CREATE TABLE temoin(id int PRIMARY KEY,texte text,valeur numeric,date timestamptz); INSERT INTO temoin VALUES(1,'épreuve 😀',0,'2026-10-11T01:02:03Z'),(2,NULL,NULL,NULL)")
            temoin=tmp/'temoin.dump';hash_temoin=dump_snapshot(bin,'qualification_synthetique',temoin,isole)
            restaure=proteger(temoin,'temoin.dump')
            testdump=isole/'temoin.dump';shutil.copyfile(restaure,testdump);os.chown(testdump,postgres.pw_uid,postgres.pw_gid)
            sql(bin,isole,'postgres','CREATE DATABASE qualification_restauree')
            commande(['runuser','-u','postgres','--',bin/'pg_restore','--exit-on-error','--no-owner','--no-acl','--host='+str(isole),'--dbname=qualification_restauree',testdump])
            exiger(schema(lambda q:sql(bin,isole,'qualification_restauree',q))==hash_temoin)
            autre=tmp/'autre.key';commande([age/'age-keygen','--output',autre])
            rejet=subprocess.run([str(age/'age'),'--decrypt','-i',str(autre),str(destination/'temoin.dump.age')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
            exiger(rejet.returncode!=0)
            (destination/'temoin.dump.age').unlink();fichiers.pop('temoin.dump.age')
            sql(bin,isole,'postgres','DROP DATABASE qualification_synthetique; DROP DATABASE qualification_restauree')
            ETAPE='snapshot-et-chiffrement'
            for base in BASES:
                dump=tmp/(base+'.dump');empreintes[base]=dump_snapshot(bin,base,dump)
                restored=proteger(dump,base+'.dump')
                cible=isole/(base+'.dump');shutil.copyfile(restored,cible);cible.chmod(0o600);os.chown(cible,postgres.pw_uid,postgres.pw_gid)
                dump.unlink();restored.unlink()
            ETAPE='copies-durables'
            sqlite={
                'sessions':'/var/lib/mrj-auth/sessions.sqlite','cycle':'/var/lib/vision-cycle/courriels.sqlite',
                'admissions':'/var/lib/mrjam-admission/admissions.sqlite','admission-courriel':'/var/lib/mrjam-admission/courriels.sqlite',
                'fermetures':'/var/lib/mrjam-fermeture/courriels.sqlite','courriel':'/var/lib/mrjam-courriel/file.sqlite'}
            for nom,path in sqlite.items():
                source=Path(path)
                if source.exists():
                    copie=tmp/(nom+'.sqlite');copie_sqlite(source,copie);proteger(copie,nom+'.sqlite')
            for nom,path in {'effacements':'/var/lib/vision-effacements/demandes.jsonl','effacements-cycle':'/var/lib/vision-cycle/effacements.jsonl','effacements-communs':'/var/lib/mrjam-fermeture/effacements.jsonl'}.items():
                source=Path(path)
                if source.exists():
                    copie=tmp/(nom+'.jsonl');copie_registre(source,copie);proteger(copie,nom+'.jsonl')
            ETAPE='restauration-isolee'
            for role in ('vision','vision_migration','vision_identite','vision_administration','vision_cycle','vision_admission','vision_fermeture','matheval','keycloak'):
                sql(bin,isole,'postgres','CREATE ROLE '+identifiant(role)+' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
            for base in BASES:
                sql(bin,isole,'postgres','CREATE DATABASE '+identifiant(base))
                commande(['runuser','-u','postgres','--',bin/'pg_restore','--exit-on-error','--no-owner','--no-acl','--host='+str(isole),'--dbname='+base,isole/(base+'.dump')])
                exiger(schema(lambda q:sql(bin,isole,base,q))==empreintes[base])
            ETAPE='invariants-finaux'
            exiger(services()==avant_services and str(Path('/run/current-system').resolve())==GENERATION)
            rapport={'format':1,'infrastructure':revision,'generation':GENERATION,'sauvegarde':tag,'bases':list(BASES),
                     'tables_restaurees':{b:len(v) for b,v in empreintes.items()},'empreintes_semantiques_identiques':True,
                     'age_dechiffrement_verifie':True,'cle_ephemere_enveloppee_pour_destinataire_existant':True,
                     'cle_personnelle_non_utilisee':True,'sqlite_copie_et_integrite':True,
                     'registre_externe_recent_requis':True,'retour_applicatif_qualifie':False,
                     'roles_restaures':False,'acl_qualification_separee_requise':True,
                     'production_sql_ecriture':False,'production_services_interrompus':False,'fichiers_chiffres':fichiers}
            # Preuve privée : les empreintes par table ne sont pas publiées.
            (destination/'empreintes-privees.json').write_text(json.dumps(empreintes,indent=2)+'\n')
            (destination/'qualification.json').write_text(json.dumps(rapport,indent=2)+'\n')
            fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            print(json.dumps({k:v for k,v in rapport.items() if k!='fichiers_chiffres'}),flush=True)
    finally:
        if actif:
            try:commande(['runuser','-u','postgres','--',bin/'pg_ctl','-D',isole/'data','-m','fast','-w','-t','20','stop'])
            except Exception:
                commande(['runuser','-u','postgres','--',bin/'pg_ctl','-D',isole/'data','-m','immediate','-w','-t','10','stop'])
        exiger(not (isole/'data/postmaster.pid').exists())
        shutil.rmtree(isole) # Seulement le répertoire unique créé dans cet appel.

if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception:
        print(json.dumps({'sauvegarde':'interrompue','etape':ETAPE,'donnees_affichees':False,'production_sql_ecriture':False}),file=sys.stderr)
        sys.exit(1)
