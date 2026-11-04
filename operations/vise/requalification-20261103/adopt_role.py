"""Fixed offline ViSe capture. Private data never leaves the VPS or enters output."""
import fcntl, hashlib, json, os, pwd, stat, subprocess
from pathlib import Path

CURRENT='/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git'
PG='/nix/store/f5bx5vyjvfc52a93q6p7gy7aidwg3jpx-postgresql-17.11/bin/'
SYSTEMCTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
DEST=Path('/var/lib/mrjam-cutover/vise-adoption-20261103')
LEDGER=Path('/var/lib/etp-carnet/deletions.log')

def require(value, code):
    if not value: raise RuntimeError(code)

def pg_identity():
    p=pwd.getpwnam('postgres');os.setgroups([]);os.setgid(p.pw_gid);os.setuid(p.pw_uid)

def offline():
    require(all(os.path.realpath(p)==CURRENT for p in ['/run/current-system','/nix/var/nix/profiles/system']),'GENERATION_CHANGED')
    r=subprocess.run([SYSTEMCTL,'show','vise.service','-p','ActiveState','--value'],capture_output=True,timeout=10)
    require(r.returncode==0 and r.stdout.strip()==b'inactive','VISE_NOT_OFFLINE')
    r=subprocess.run([PG+'psql','-XwqAt','-h','/run/postgresql','-d','postgres','-c',
        "SELECT count(*) FROM pg_stat_activity WHERE datname='etp_carnet'"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,preexec_fn=pg_identity,
        env={'LC_ALL':'C','PGCONNECT_TIMEOUT':'5'})
    require(r.returncode==0 and r.stdout.strip()==b'0','VISE_CONNECTION_PRESENT')
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try: require(p.stat().st_uid!=981,'VISE_PROCESS_PRESENT')
            except FileNotFoundError: pass

def metadata(path, mode, uid, directory=False):
    s=path.lstat()
    require((stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1)
            and stat.S_IMODE(s.st_mode)==mode and s.st_uid==s.st_gid==uid,'METADATA_REFUSED')
    return s

def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def save(name, value):
    with (DEST/name).open('x') as f:
        json.dump(value,f,sort_keys=True);f.flush();os.fsync(f.fileno())


QUERY="BEGIN READ ONLY; SET LOCAL statement_timeout='3s'; SET LOCAL ROLE etp_carnet;\n\nSELECT json_build_object(\n 'context', current_user='etp_carnet' AND current_database()='etp_carnet'\n   AND current_setting('server_version_num')::int BETWEEN 170000 AND 179999,\n 'versions', (SELECT json_agg(version ORDER BY version) FROM public.schema_migrations),\n 'columns', (SELECT json_object_agg(name, cols) FROM (\n   SELECT c.relname AS name, json_agg(json_build_object('name',a.attname,\n     'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull) ORDER BY a.attnum) AS cols\n   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace\n   JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped\n   WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') GROUP BY c.relname) entries),\n 'primary_keys', (SELECT json_object_agg(name, cols) FROM (\n   SELECT c.relname AS name, json_agg(a.attname ORDER BY k.position) AS cols\n   FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace\n   CROSS JOIN LATERAL unnest(x.conkey) WITH ORDINALITY k(attnum,position)\n   JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum\n   WHERE n.nspname='public' AND x.contype='p' GROUP BY c.relname) entries),\n 'unique_keys', (SELECT json_object_agg(name, keys) FROM (\n   SELECT name,json_agg(cols ORDER BY id) AS keys FROM (\n     SELECT x.oid AS id,c.relname AS name,json_agg(a.attname ORDER BY k.position) AS cols\n     FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace\n     CROSS JOIN LATERAL unnest(x.conkey) WITH ORDINALITY k(attnum,position)\n     JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum\n     WHERE n.nspname='public' AND x.contype='u' GROUP BY x.oid,c.relname) keys GROUP BY name) entries),\n 'cascade_accounts', (SELECT json_agg(c.relname ORDER BY c.relname) FROM pg_constraint x\n   JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace\n   WHERE n.nspname='public' AND x.contype='f' AND x.confrelid='public.comptes'::regclass\n     AND x.confdeltype='c' AND x.convalidated AND NOT x.condeferrable\n     AND x.conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=c.oid AND attname='compte')]\n     AND x.confkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=x.confrelid AND attname='id')]),\n 'runtime_ddl_forbidden', NOT (\n   has_database_privilege(current_user,current_database(),'CREATE') OR\n   has_database_privilege(current_user,current_database(),'TEMP') OR\n   EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname<>'information_schema'\n     AND has_schema_privilege(current_user,oid,'CREATE')) OR\n   EXISTS (SELECT FROM pg_roles WHERE rolname=current_user AND\n     (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) OR\n   EXISTS (SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR\n   EXISTS (SELECT FROM pg_database WHERE datname=current_database() AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR\n   EXISTS (SELECT FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR\n   EXISTS (SELECT FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR\n   EXISTS (SELECT FROM pg_type WHERE typowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR\n   EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace\n     WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND p.prosecdef\n       AND has_function_privilege(current_user,p.oid,'EXECUTE'))\n )\n);\n\nROLLBACK;"
EXPECTED={'versions': [1], 'columns': {'archives': [{'name': 'id', 'not_null': True, 'type': 'uuid'}, {'name': 'compte', 'not_null': True, 'type': 'uuid'}, {'name': 'payload', 'not_null': True, 'type': 'jsonb'}, {'name': 'images', 'not_null': True, 'type': 'jsonb'}, {'name': 'created_at', 'not_null': True, 'type': 'timestamp with time zone'}], 'coffres': [{'name': 'compte', 'not_null': True, 'type': 'uuid'}, {'name': 'revision', 'not_null': True, 'type': 'bigint'}, {'name': 'payload', 'not_null': True, 'type': 'jsonb'}, {'name': 'updated_at', 'not_null': True, 'type': 'timestamp with time zone'}], 'comptes': [{'name': 'id', 'not_null': True, 'type': 'uuid'}, {'name': 'pseudonyme', 'not_null': True, 'type': 'text'}, {'name': 'password_hash', 'not_null': True, 'type': 'text'}, {'name': 'auth_recovery_hash', 'not_null': True, 'type': 'text'}, {'name': 'created_at', 'not_null': True, 'type': 'timestamp with time zone'}, {'name': 'last_seen', 'not_null': True, 'type': 'timestamp with time zone'}], 'objets': [{'name': 'compte', 'not_null': True, 'type': 'uuid'}, {'name': 'id', 'not_null': True, 'type': 'uuid'}, {'name': 'payload', 'not_null': True, 'type': 'jsonb'}], 'schema_migrations': [{'name': 'version', 'not_null': True, 'type': 'integer'}, {'name': 'applied_at', 'not_null': True, 'type': 'timestamp with time zone'}], 'sessions': [{'name': 'token_hash', 'not_null': True, 'type': 'text'}, {'name': 'compte', 'not_null': True, 'type': 'uuid'}, {'name': 'csrf', 'not_null': True, 'type': 'text'}, {'name': 'expires_at', 'not_null': True, 'type': 'timestamp with time zone'}, {'name': 'last_seen', 'not_null': True, 'type': 'timestamp with time zone'}], 'suppressions': [{'name': 'compte', 'not_null': True, 'type': 'uuid'}, {'name': 'deleted_at', 'not_null': True, 'type': 'timestamp with time zone'}]}, 'primary_keys': {'archives': ['id'], 'coffres': ['compte'], 'comptes': ['id'], 'objets': ['compte', 'id'], 'schema_migrations': ['version'], 'sessions': ['token_hash'], 'suppressions': ['compte']}, 'unique_keys': {'comptes': [['pseudonyme']]}, 'cascade_accounts': ['archives', 'coffres', 'objets', 'sessions']}
ADOPT="-- Fixed, explicit PostgreSQL adoption operation. Not executed by a NixOS\n-- activation or service start. Backup/restore and release admission precede it.\n-- Run only in the existing etp_carnet database as the local PostgreSQL operator.\nBEGIN;\nSET LOCAL lock_timeout = '5s';\nSET LOCAL statement_timeout = '30s';\nDO $adoption$\nDECLARE runtime_oid oid;\nBEGIN\n  IF current_database() <> 'etp_carnet' OR current_user <> 'postgres' THEN\n    RAISE EXCEPTION 'VISE_ADOPTION_CONTEXT_REFUSED';\n  END IF;\n  SELECT oid INTO STRICT runtime_oid FROM pg_roles WHERE rolname = 'etp_carnet';\n  IF EXISTS (SELECT FROM pg_roles WHERE oid = runtime_oid AND\n      (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))\n     OR EXISTS (SELECT FROM pg_auth_members WHERE member = runtime_oid)\n     OR EXISTS (SELECT FROM pg_database WHERE datdba = runtime_oid AND datname <> 'etp_carnet')\n     OR EXISTS (SELECT FROM pg_tablespace WHERE spcowner = runtime_oid) THEN\n    RAISE EXCEPTION 'VISE_ADOPTION_PRIVILEGES_REFUSED';\n  END IF;\n  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_vise_schema') THEN\n    CREATE ROLE mrjam_vise_schema NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;\n  END IF;\n  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mrjam_vise_schema' AND\n      (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))\n     OR EXISTS (SELECT FROM pg_auth_members WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_vise_schema')\n        OR member = (SELECT oid FROM pg_roles WHERE rolname = 'mrjam_vise_schema')) THEN\n    RAISE EXCEPTION 'VISE_ADOPTION_SCHEMA_ROLE_REFUSED';\n  END IF;\nEND\n$adoption$;\nREASSIGN OWNED BY etp_carnet TO mrjam_vise_schema;\nALTER DATABASE etp_carnet OWNER TO mrjam_vise_schema;\nREVOKE CREATE, TEMPORARY ON DATABASE etp_carnet FROM PUBLIC, etp_carnet;\nREVOKE CREATE ON SCHEMA public FROM PUBLIC, etp_carnet;\nGRANT CONNECT ON DATABASE etp_carnet TO etp_carnet;\nGRANT USAGE ON SCHEMA public TO etp_carnet;\nGRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO etp_carnet;\nGRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO etp_carnet;\nALTER DEFAULT PRIVILEGES FOR ROLE mrjam_vise_schema IN SCHEMA public\n  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etp_carnet;\nALTER DEFAULT PRIVILEGES FOR ROLE mrjam_vise_schema IN SCHEMA public\n  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO etp_carnet;\nCOMMIT;\n"

def sql(query):
    r=subprocess.run([PG+'psql','-XwqAt','-h','/run/postgresql','-d','etp_carnet','-v','ON_ERROR_STOP=1'],input=query.encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45,preexec_fn=pg_identity,env={'LC_ALL':'C','PGCONNECT_TIMEOUT':'5'})
    require(r.returncode==0 and len(r.stdout)<=65536,'SQL_OPERATION_REFUSED')
    return r.stdout

def schema():
    v=json.loads(sql(QUERY));require(v['context'] is True and all(v.get(k)==x for k,x in EXPECTED.items()),'SCHEMA_REFUSED');return v

def main():
    require(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED');os.umask(0o077)
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);offline();metadata(DEST,0o700,0,True)
        metadata(DEST/'captured.json',0o600,0);receipt=json.loads((DEST/'captured.json').read_text())
        require(receipt['phase']=='offline-capture-verified','CAPTURE_REFUSED')
        for n in ['database.dump','deletions.log']:
            metadata(DEST/n,0o600,0);require(digest(DEST/n)==receipt['files'][n]['sha256'],'CAPTURE_CHANGED')
        require(digest(LEDGER)==receipt['files']['deletions.log']['sha256'],'LEDGER_CHANGED')
        schema();sql(ADOPT)
        require(schema()['runtime_ddl_forbidden'] is True,'RUNTIME_DDL_RETAINED')
        save('adopted.json',{'schema_version':1,'phase':'restricted-role-verified'})
        print(json.dumps({'schema_version':1,'code':'VISE_ROLE_ADOPTED','schema_matches_v1':True,'runtime_ddl_forbidden':True,'application_started':False,'database_restored':False}))
    finally:os.close(lock)
if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'code':'VISE_ROLE_ADOPTION_REFUSED','reason':str(e) if type(e) is RuntimeError else type(e).__name__}));raise SystemExit(1)
