"""Disposable verifier-owned PostgreSQL, never a production connection.

The candidate can reach loopback but receives only the restricted runtime
identity. Administrative authentication and the data directory remain outside
the candidate's PID and mount namespaces. All schema inputs are protected code.
"""
import json,os,secrets,subprocess,time
from pathlib import Path
import source_policy as P
import sandbox

class Database:
    def __init__(self,build):
        self.build=build;self.tools=build.tools
        self.root=build.private/'postgres';self.root.mkdir(mode=0o700)
        self.data=self.root/'data';self.started=False
        self.empty=self.root/'empty';self.empty.mkdir(mode=0o700)
        self.process=None
        self.password=secrets.token_hex(32)
        self.runtime_password=secrets.token_hex(32)
        self.env={'PATH':build.runtime['path'],'HOME':str(self.root),'LANG':'C.UTF-8',
            'PGCONNECT_TIMEOUT':'5','PGPASSWORD':self.password,
            'PGOPTIONS':'-c statement_timeout=10000 -c lock_timeout=5000'}
        self.connection=['-h','127.0.0.1','-p','55432','-U','postgres','-d','etp_carnet']

    def command(self,argv,*,input=None,env=None,ok=True,timeout=30):
        result=subprocess.run(argv,input=input,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env=self.env if env is None else env,timeout=timeout,check=False)
        P.require(len(result.stdout)<=65536,'VISE_SYNTHETIC_OUTPUT_LIMIT')
        if ok:P.require(result.returncode==0,'VISE_SYNTHETIC_DATABASE_FAILED')
        return result

    def sql(self,statement,*,runtime=False,ok=True):
        connection=list(self.connection);env=dict(self.env)
        if runtime:
            connection[connection.index('-U')+1]='etp_carnet'
            env['PGPASSWORD']=self.runtime_password
        return self.command([self.tools['psql'],*connection,'-X','-w','-At',
            '-v','ON_ERROR_STOP=1','-c',statement],env=env,ok=ok)

    def start(self):
        password_file=self.root/'initial-password'
        password_file.write_text(self.password+'\n');password_file.chmod(0o600)
        def isolated(argv):
            return sandbox.command(self.tools['bwrap'],{'shell':self.tools['shell']},
                self.empty,self.root,self.build.passwd,argv,
                {'PATH':self.build.runtime['path'],'HOME':'/job','LANG':'C.UTF-8','TMPDIR':'/tmp'},cwd='/job')
        P.require(sandbox.run(isolated([self.tools['initdb'],'-D','/job/data','--username=postgres',
            '--auth-local=reject','--auth-host=scram-sha-256','--encoding=UTF8',
            '--locale=C','--pwfile=/job/initial-password']),timeout=120)==0,'VISE_SYNTHETIC_INITDB_FAILED')
        password_file.unlink()
        with (self.data/'postgresql.conf').open('a') as stream:
            stream.write("\nlisten_addresses='127.0.0.1'\nport=55432\nunix_socket_directories=''\n"
                "max_connections=24\nshared_buffers='32MB'\nmax_wal_size='96MB'\n"
                "min_wal_size='32MB'\nfsync=on\nlogging_collector=off\nlog_statement='none'\n")
        postgres=str(Path(self.tools['pg_ctl']).with_name('postgres'))
        self.process=sandbox.start(isolated([postgres,'-D','/job/data']))
        self.started=True
        for attempt in range(100):
            probe=self.command([self.tools['psql'],'-h','127.0.0.1','-p','55432',
                '-U','postgres','-d','postgres','-X','-w','-At','-c','SELECT 1'],ok=False)
            if probe.returncode==0:break
            P.require(self.process.poll() is None,'VISE_SYNTHETIC_POSTGRES_EXITED')
            time.sleep(0.1)
        else:raise P.Refused('VISE_SYNTHETIC_POSTGRES_TIMEOUT')
        self.command([self.tools['createdb'],'-h','127.0.0.1','-p','55432','-U','postgres','etp_carnet'])
        self.sql("CREATE ROLE etp_carnet LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '"+self.runtime_password+"'")
        # Explicitly deny access to all databases except the synthetic app DB.
        (self.data/'pg_hba.conf').write_text(
            'host all postgres 127.0.0.1/32 scram-sha-256\n'
            'host etp_carnet etp_carnet 127.0.0.1/32 scram-sha-256\n'
            'host all all 127.0.0.1/32 reject\n')
        self.sql('SELECT pg_reload_conf()')

    def initialize(self):
        self.sql(Path(self.build.runtime['vise_schema']).read_text())
        # The production adoption script is fixed, not sourced from a candidate.
        for _ in range(2):self.sql(Path(self.build.runtime['vise_adopt_role']).read_text())

    def metadata(self):
        # Import only the protected preflight query, never its production main.
        import importlib.util
        spec=importlib.util.spec_from_file_location('vise_schema_check',self.build.runtime['vise_adoption_check'])
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        observed=json.loads(self.sql(module.QUERY,runtime=True).stdout)
        contract=json.loads(Path(self.build.runtime['vise_schema_contract']).read_bytes())
        expected={key:contract[key] for key in ['versions','columns','primary_keys','unique_keys','cascade_accounts']}
        expected.update(context=True,runtime_ddl_forbidden=True)
        return observed==expected

    def stop(self):
        if self.started:
            # This is a disposable cluster, outside the candidate namespace.
            # Destroy the entire PostgreSQL namespace including its children.
            sandbox.stop(self.process)
            self.started=False
