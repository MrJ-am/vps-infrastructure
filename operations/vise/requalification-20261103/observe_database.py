"""Fixed read-only database/role facts and availability of the retained UID."""
import json,os,pwd,subprocess
PSQL='/nix/store/f5bx5vyjvfc52a93q6p7gy7aidwg3jpx-postgresql-17.11/bin/psql'
QUERY="""BEGIN READ ONLY;
SET LOCAL statement_timeout='3s';
SELECT json_build_object(
 'database_present', EXISTS(SELECT FROM pg_database WHERE datname='etp_carnet'),
 'runtime_role_present', EXISTS(SELECT FROM pg_roles WHERE rolname='etp_carnet'),
 'runtime_role_login', EXISTS(SELECT FROM pg_roles WHERE rolname='etp_carnet' AND rolcanlogin),
 'runtime_role_privileged', EXISTS(SELECT FROM pg_roles WHERE rolname='etp_carnet' AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)),
 'runtime_role_owns_database', EXISTS(SELECT FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname='etp_carnet' AND r.rolname='etp_carnet'),
 'schema_owner_role_present', EXISTS(SELECT FROM pg_roles WHERE rolname='mrjam_vise_schema'),
 'active_connections', (SELECT count(*) FROM pg_stat_activity WHERE datname='etp_carnet')
);
ROLLBACK;
"""
def main():
 assert os.geteuid()==0 and os.uname().nodename=='srv1982677'
 pg=pwd.getpwnam('postgres')
 def identity():os.setgroups([]);os.setgid(pg.pw_gid);os.setuid(pg.pw_uid)
 p=subprocess.run([PSQL,'-X','-w','-qAt','-h','/run/postgresql','-d','postgres','-v','ON_ERROR_STOP=1'],input=QUERY.encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,preexec_fn=identity,env={'LC_ALL':'C','PGCONNECT_TIMEOUT':'5'})
 assert p.returncode==0 and len(p.stdout)<4096
 value=json.loads(p.stdout)
 try:account=pwd.getpwuid(981);value['retained_uid_available']=account.pw_name=='etp_carnet'
 except KeyError:value['retained_uid_available']=True
 value.update(schema_version=1,code='VISE_DATABASE_METADATA',read_only=True)
 print(json.dumps(value,sort_keys=True))
if __name__=='__main__':main()
