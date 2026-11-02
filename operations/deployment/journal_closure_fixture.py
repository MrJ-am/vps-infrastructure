"""Independent synthetic VM fixture; no production inputs or access."""
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SOURCE = Path('/etc/synthetic-worker-source')
BOOTSTRAP = Path('/etc/synthetic-journal-bootstrap/bootstrap-journal')
CORRECTION = '/etc/synthetic-journal-correction.sql'
UNIT = 'mrjam-vision-closure.service'
ROLES = ('vision_journal_writer','vision_journal_archiviste','vision_journal_rejeu','vision_journal_fermeture')
STATE = Path('/run/synthetic-journal-proof')


def command(args, data=None, success=True):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    assert (result.returncode == 0) == success, (args[0], result.returncode, result.stderr.decode()[:2000])
    return result.stdout.decode().strip()


def sql(query=None, database='vision_journal', file=None, role='postgres', user='postgres', success=True):
    args = ['runuser','-u',user,'--','psql','-X','-w','-qAt','-v','ON_ERROR_STOP=1',
            '-h','/run/postgresql','-U',role,'-d',database]
    if file:args += ['-f',str(file)]
    return command(args, query.encode() if query else None, success)


def properties():
    raw = command(['systemctl','show',UNIT,'--property=MainPID,ExecStartPre,ActiveState,SubState,Result'])
    return dict(line.split('=',1) for line in raw.splitlines())


def acl():
    return sql("SELECT json_build_object('tables',(SELECT json_agg(row(c.relname,c.relacl)::text ORDER BY c.relname) "
      "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vision_effacements' AND c.relkind='r'),"
      "'functions',(SELECT json_agg(row(p.oid::regprocedure::text,p.proacl)::text ORDER BY p.oid::regprocedure::text) "
      "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='vision_effacements'))::text")


def writer_predicate():
    text = (SOURCE/'src/journal_postgres.rs').read_text()
    matches = re.findall(r'const PRECONDITIONS: &str = r#"(.*?)"#;',text,re.S)
    assert len(matches)==1
    return matches[0]


def prepare():
    STATE.mkdir(mode=0o700)
    command(['runuser','-u','postgres','--','createdb','vision'])
    sql('CREATE EXTENSION vector;',database='vision')
    migrations = sorted((SOURCE/'migrations').glob('[0-9]*.sql'))
    assert len(migrations)==27
    for path in migrations:sql(database='vision',file=path)
    sql(database='vision',file=SOURCE/'scripts/roles.sql')
    for database,name in [('postgres','01-roles.sql'),('postgres','02-database.sql'),('vision_journal','03-schema.psql')]:
        sql(database=database,file=BOOTSTRAP/name)
    secret = Path('/var/lib/mrjam-worker-credentials/v1/closure')
    secret.parent.mkdir(parents=True,mode=0o700)
    secret.write_text('INVENTED-CLOSURE-CREDENTIAL-ONLY-1234567890')
    secret.chmod(0o600)
    (STATE/'acl-before.json').write_text(acl())
    for role in ROLES:
        assert sql("SELECT has_schema_privilege('"+role+"','public','USAGE')::text")=='false'
    sql(writer_predicate(),role='vision_journal_writer',user='synthetic-journal-writer',success=False)


def old_failure():
    value=properties()
    assert value['ActiveState']=='failed' and value['MainPID']=='0' and value['Result']=='exit-code'
    assert 'code=exited' in value['ExecStartPre'] and 'status=1' in value['ExecStartPre']
    assert command(['curl','--silent','--max-time','2','http://127.0.0.1:3028/'],success=False)==''


def correct():
    sql(file=CORRECTION)
    assert acl()==(STATE/'acl-before.json').read_text()


def running():
    value=properties()
    assert value['ActiveState']=='active' and value['SubState']=='running' and int(value['MainPID'])>0
    assert 'code=exited' in value['ExecStartPre'] and 'status=0' in value['ExecStartPre']
    status=Path('/proc/'+value['MainPID']+'/status').read_text()
    assert re.search(r'^Uid:\s+946\s+946\s+946\s+946$',status,re.M)
    connection=HTTPConnection('127.0.0.1',3028,timeout=5)
    connection.request('POST','/fermer',body=b'{}',headers={'Content-Type':'application/json'})
    response=connection.getresponse();body=response.read();connection.close()
    assert response.status==403 and len(body)<1024
    assert acl()==(STATE/'acl-before.json').read_text()


def boundaries():
    for role in ROLES:
        assert sql("SELECT has_schema_privilege('"+role+"','public','USAGE')::text")=='true'
        assert sql("SELECT has_schema_privilege('"+role+"','public','CREATE')::text")=='false'
        assert sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='vision_effacements' AND c.relkind='r' AND has_table_privilege('"+role+"',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')")=='0'
    assert sql("SELECT has_schema_privilege('vision_journal_import','public','USAGE')::text")=='false'
    assert sql("SELECT rolcanlogin::text FROM pg_roles WHERE rolname='vision_journal_import'")=='false'
    assert sql("SELECT count(*) FROM pg_namespace n,aclexplode(n.nspacl) a WHERE n.nspname='public' AND a.grantee=0")=='0'
    assert acl()==(STATE/'acl-before.json').read_text()


def repeat_and_wrong_database():
    sql(file=CORRECTION)
    sql(file=CORRECTION,database='vision',success=False)
    boundaries()


def writer():
    assert sql(writer_predicate(),role='vision_journal_writer',user='synthetic-journal-writer')=='t'


def no_events():
    assert sql('SELECT count(*) FROM vision_effacements.demandes')=='0'
    assert sql('SELECT count(*) FROM vision_effacements.fermetures')=='0'
    assert acl()==(STATE/'acl-before.json').read_text()


if __name__=='__main__':
    actions={'prepare':prepare,'old-failure':old_failure,'correct':correct,'running':running,
        'boundaries':boundaries,'repeat-and-wrong-database':repeat_and_wrong_database,'writer':writer,'no-events':no_events}
    assert len(sys.argv)==2 and sys.argv[1] in actions and os.geteuid()==0
    actions[sys.argv[1]]()
    print(json.dumps({'schema_version':1,'check':sys.argv[1],'passed':True}))
