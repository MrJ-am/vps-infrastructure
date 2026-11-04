"""Independent runtime observations of the freshly built ViSe candidate.

Uses only a disposable SQL cluster and invented application fixtures. Database
administration and the current erasure ledger never enter the API-test sandbox.
"""
import json,os,stat,time,urllib.request,uuid
from pathlib import Path
import sandbox,source_policy as P
from synthetic_database import Database

class Runtime:
    def __init__(self,build):
        self.build=build;self.db=Database(build);self.process=None
        self.scratch=Path('/work/vise-runtime');self.scratch.mkdir(mode=0o700)
        self.tests=Path('/work/vise-api');self.tests.mkdir(mode=0o700)
        self.ledger=self.scratch/'deletions.log';self.ledger.write_bytes(b'');self.ledger.chmod(0o600)
        self.configuration=build.private/'runtime.json'
        self.configuration.write_text(json.dumps({'password':self.db.runtime_password,'node':build.tools['node']}))
        self.configuration.chmod(0o400)
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def command(self,mode):
        b=self.build
        readonly=[(self.configuration,'/support/runtime.json'),(b.server,'/support/server'),
            (b.dist,'/support/dist'),(Path(b.runtime['vise_runtime_entry']),'/support/entry.py')]
        if mode=='api':readonly.append((Path(b.runtime['vise_api_tests']),'/support/api-tests.mjs'))
        return sandbox.command(b.tools['bwrap'],{'shell':b.tools['shell']},
            b.job/'project' if mode=='api' else b.source,self.tests if mode=='api' else self.scratch,
            b.passwd,[b.tools['python'],'-I','-S','/support/entry.py',mode],
            b.env,readonly=readonly,cwd='/source' if mode=='api' else '/job')

    def get(self,path):
        with self.http.open('http://127.0.0.1:3017'+path,timeout=3) as response:
            raw=response.read(8*1024**2+1)
            P.require(response.status==200 and len(raw)<=8*1024**2,'VISE_HTTP_REFUSED')
            return raw

    def start(self):
        P.require(self.process is None,'VISE_RUNTIME_ALREADY_STARTED')
        self.preflight()
        (self.scratch/'stop').unlink(missing_ok=True)
        self.process=sandbox.start(self.command('serve'))
        for _ in range(100):
            P.require(self.process.poll() is None,'VISE_RUNTIME_EXITED')
            try:
                if json.loads(self.get('/api/health'))=={'prototype':True,'status':'ok'}:return
            except (OSError,ValueError):pass
            time.sleep(0.1)
        raise P.Refused('VISE_RUNTIME_TIMEOUT')

    def stop(self):
        P.require(self.process is not None and self.process.poll() is None,'VISE_RUNTIME_EXITED')
        fd=os.open(self.scratch/'stop',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        P.require(self.process.wait(timeout=40)==0,'VISE_GRACEFUL_STOP_FAILED')
        self.process=None

    def preflight(self):
        info=self.ledger.lstat()
        P.require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
            and info.st_nlink==1 and info.st_uid==os.getuid() and info.st_size<=1024*1024,
            'VISE_LEDGER_PREFLIGHT_FAILED')
        P.require(self.db.metadata(),'VISE_SCHEMA_PREFLIGHT_FAILED')

    def refused_preflight(self):
        try:self.preflight()
        except (P.Refused,OSError):return
        raise P.Refused('VISE_INVALID_STATE_ACCEPTED')

    def run(self):
        b=self.build
        try:
            self.db.start();self.db.initialize()
            P.require(self.db.metadata(),'VISE_SCHEMA_PREFLIGHT_FAILED')
            self.db.sql('UPDATE schema_migrations SET version=2');self.refused_preflight()
            self.db.sql('UPDATE schema_migrations SET version=1')
            self.db.sql('ALTER TABLE comptes ADD COLUMN synthetic_extra integer');self.refused_preflight()
            self.db.sql('ALTER TABLE comptes DROP COLUMN synthetic_extra')
            self.db.sql('GRANT CREATE ON SCHEMA public TO etp_carnet');self.refused_preflight()
            self.db.sql('REVOKE CREATE ON SCHEMA public FROM etp_carnet')
            saved=self.scratch/'saved-ledger';self.ledger.rename(saved);self.refused_preflight()
            self.ledger.symlink_to(saved);self.refused_preflight();self.ledger.unlink();saved.rename(self.ledger)
            self.ledger.chmod(0o644);self.refused_preflight();self.ledger.chmod(0o600)
            P.require(self.db.sql('CREATE TABLE forbidden(id int)',runtime=True,ok=False).returncode!=0,
                'VISE_RUNTIME_DDL_ALLOWED')
            self.start()
            P.require(self.get('/elm.js')==(b.dist/'elm.js').read_bytes(),'VISE_FRONTEND_HTTP_MISMATCH')
            P.require(sandbox.run(self.command('api'),timeout=600)==0,'VISE_API_TESTS_FAILED')
            P.require(self.db.metadata(),'VISE_SCHEMA_CHANGED')
            b.steps.append({'name':'vise-api-tests-synthetic-postgresql','status':'passed'})
            b.steps.append({'name':'vise-schema-and-role-refusals','status':'passed'})
            self.stop();ledger=P.read(self.ledger,1024*1024)
            P.require(bool(ledger),'VISE_ERASURE_FIXTURE_MISSING')
            self.start();P.require(P.read(self.ledger,1024*1024)==ledger,'VISE_LEDGER_CHANGED')
            self.stop()
            b.steps.append({'name':'vise-graceful-stop-and-restart','status':'passed'})
            deleted=ledger.decode('ascii').splitlines()[0]
            P.require(str(uuid.UUID(deleted))==deleted,'VISE_ERASURE_UUID_REFUSED')
            self.db.sql("DELETE FROM suppressions WHERE compte='"+deleted+"'::uuid")
            self.db.sql("INSERT INTO comptes(id,pseudonyme,password_hash,auth_recovery_hash) VALUES('"+deleted+
                "'::uuid,'synthetic_restored_deleted','synthetic','synthetic')")
            payload=self.db.sql("SELECT md5(string_agg(payload::text,',' ORDER BY compte::text)) FROM coffres").stdout
            P.require(len(payload.strip())==32,'VISE_SURVIVING_FIXTURE_MISSING')
            dump=b.private/'synthetic.dump'
            pg_bin=Path(b.tools['pg_ctl']).parent
            self.db.command([str(pg_bin/'pg_dump'),*self.db.connection,'-Fc','--no-owner','--no-privileges','-f',str(dump)],timeout=120)
            self.start()
            count="SELECT count(*) FROM comptes WHERE id='"+deleted+"'::uuid"
            P.require(self.db.sql(count).stdout.strip()==b'0','VISE_ERASURE_REPLAY_FAILED');self.stop()
            self.db.command([str(pg_bin/'pg_restore'),*self.db.connection,'--clean','--if-exists',
                '--no-owner','--no-privileges',str(dump)],timeout=120)
            self.db.sql(Path(b.runtime['vise_adopt_role']).read_text())
            P.require(self.db.sql(count).stdout.strip()==b'1','VISE_RESTORE_FIXTURE_FAILED')
            P.require(P.read(self.ledger,1024*1024)==ledger,'VISE_LEDGER_CHANGED')
            self.start()
            P.require(self.db.sql(count).stdout.strip()==b'0','VISE_ERASURE_RESURRECTED')
            P.require(self.db.sql("SELECT md5(string_agg(payload::text,',' ORDER BY compte::text)) FROM coffres").stdout==payload,
                'VISE_SURVIVING_DATA_CHANGED')
            P.require(self.db.metadata(),'VISE_RESTORED_SCHEMA_CHANGED');self.stop()
            b.steps.append({'name':'vise-restore-current-erasure-ledger','status':'passed'})
        finally:
            if self.process is not None:sandbox.stop(self.process)
            self.db.stop()
