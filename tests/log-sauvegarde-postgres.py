"""Dump/restauration PG réel sans PGHOST hérité ; aucune donnée de production."""
import subprocess
import json
import time
import uuid

IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'

def main():
    nom='mrjam-backup-socket-'+uuid.uuid4().hex[:12]
    def docker(*args,input=None,check=True):
        return subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],input=input,
                              capture_output=True,check=check,timeout=60)
    def exec_pg(*args,input=None,check=True):
        return docker('exec','-i','-e','PGHOST=/socket-synthetique-absent',nom,*args,input=input,check=check)
    def sql(query,db='postgres'):
        return exec_pg('psql','-XAtq','--host=/var/run/postgresql','-U','postgres','-d',db,
                       '--set=ON_ERROR_STOP=1','-c',query).stdout.decode().strip()
    docker('image','inspect',IMAGE)  # Pas de pull ni d'installation implicite.
    docker('run','--detach','--name',nom,'--network=none','--tmpfs','/var/lib/postgresql/data',
           '-e','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE)
    try:
        for _ in range(100):
            logs=docker('logs',nom)
            if (b'PostgreSQL init process complete; ready for start up.' in logs.stdout+logs.stderr and
                docker('exec',nom,'pg_isready','-h','/var/run/postgresql','-U','postgres',check=False).returncode==0):break
            time.sleep(.1)
        else:raise AssertionError('PostgreSQL synthétique indisponible')
        sql('CREATE DATABASE backup_source;');sql('CREATE DATABASE backup_restore;')
        sql("CREATE TABLE temoin(id integer PRIMARY KEY,texte text,note integer); INSERT INTO temoin VALUES(1,'été et espaces',0),(2,'Ω',7);",'backup_source')
        refuse=exec_pg('pg_dump','-U','postgres','--format=custom','backup_source',check=False)
        assert refuse.returncode!=0 and b'socket-synthetique-absent' in refuse.stderr
        dump=exec_pg('pg_dump','--host=/var/run/postgresql','-U','postgres','--format=custom','backup_source').stdout
        assert dump.startswith(b'PGDMP')
        exec_pg('pg_restore','--host=/var/run/postgresql','-U','postgres','--dbname=backup_restore','--exit-on-error',input=dump)
        query='SELECT json_agg(to_jsonb(t) ORDER BY id) FROM temoin t;'
        assert sql(query,'backup_source')==sql(query,'backup_restore')
        print(json.dumps({'postgres_reel':True,'mauvais_pg_host_refuse':True,'socket_explicite_prioritaire':True,
                          'restauration_identique':True,'production':False}))
    finally:docker('rm','--force',nom)

if __name__=='__main__':main()
