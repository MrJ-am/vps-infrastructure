"""PG17 réel : chemins d'accès postmaster, restart requis et données conservées.

Conteneur jetable verrouillé/sans réseau, données synthétiques uniquement.
"""
import json
import subprocess
import time
import uuid

IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'


def verifier():
    nom='mrjam-pg-acces-'+uuid.uuid4().hex[:12]
    def docker(*args,input=None,check=True):
        return subprocess.run(['docker',*map(str,args)],input=input,text=True,capture_output=True,check=check)
    def pret():
        for _ in range(100):
            # Le serveur temporaire d'initdb ouvre déjà le socket Unix,
            # puis s'arrête. Seul le serveur final ouvre TCP sur loopback.
            if docker('exec',nom,'pg_isready','-h','127.0.0.1','-U','postgres',check=False).returncode==0:return
            time.sleep(.1)
        raise AssertionError('PostgreSQL indisponible')
    def sql(q):return docker('exec','-i',nom,'runuser','-u','postgres','--','psql','-XAtq',
        '-d','postgres','--set=ON_ERROR_STOP=1','--file=-',input=q).stdout.strip()
    docker('run','--detach','--name',nom,'--network','none','--env','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE)
    try:
        pret()
        contextes=json.loads(sql("SELECT json_object_agg(name,context) FROM pg_settings WHERE name IN ('hba_file','ident_file');"))
        assert contextes=={'hba_file':'postmaster','ident_file':'postmaster'}
        sql("CREATE ROLE fixture LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; CREATE TABLE temoin(id int PRIMARY KEY,valeur int); INSERT INTO temoin VALUES(1,0),(2,NULL);")
        avant=sql('SELECT json_agg(to_jsonb(t) ORDER BY id) FROM temoin t;')
        debut=sql('SELECT pg_postmaster_start_time();')
        pid=docker('inspect','--format={{.State.Pid}}',nom).stdout.strip()
        for f,t in [('hba-nouveau.conf','local all postgres peer\nlocal all fixture peer map=mrjam_fixture\n'),
                    ('ident-nouveau.conf','mrjam_fixture nobody fixture\n')]:
            docker('exec','-i',nom,'runuser','-u','postgres','--','sh','-c','umask 077; cat > /var/lib/postgresql/data/'+f,input=t)
        sql("ALTER SYSTEM SET hba_file='/var/lib/postgresql/data/hba-nouveau.conf'; ALTER SYSTEM SET ident_file='/var/lib/postgresql/data/ident-nouveau.conf'; SELECT pg_reload_conf();")
        for _ in range(100):
            r=json.loads(sql("SELECT json_object_agg(name,pending_restart) FROM pg_settings WHERE name IN ('hba_file','ident_file');"))
            if all(r.values()):break
            time.sleep(.05)
        else:raise AssertionError('Restart non déclaré')
        assert sql('SELECT pg_postmaster_start_time();')==debut
        assert not sql('SHOW hba_file;').endswith('hba-nouveau.conf')
        docker('restart',nom);pret()
        assert docker('inspect','--format={{.State.Pid}}',nom).stdout.strip()!=pid
        assert sql('SELECT pg_postmaster_start_time();')!=debut
        assert sql('SHOW hba_file;').endswith('hba-nouveau.conf')
        assert sql('SHOW ident_file;').endswith('ident-nouveau.conf')
        assert sql('SELECT json_agg(to_jsonb(t) ORDER BY id) FROM temoin t;')==avant
        bonne=docker('exec',nom,'runuser','-u','nobody','--','psql','-XAtq','-U','fixture','-d','postgres','-c','SELECT current_user;')
        assert bonne.stdout.strip()=='fixture'
        refuse=docker('exec',nom,'psql','-XAtq','-U','fixture','-d','postgres','-c','SELECT current_user;',check=False)
        assert refuse.returncode!=0 and 'Peer authentication failed' in refuse.stderr
        print('PG17 : hba_file/ident_file postmaster, SIGHUP insuffisant ; restart applique les chemins, données zéro/NULL conservées, UID réel requis.')
    finally:docker('rm','--force','--volumes',nom)


if __name__=='__main__':verifier()
