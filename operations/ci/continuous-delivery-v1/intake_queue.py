"""Durable intake scheduling metadata; a queue state grants no CI authority.

Only the intake principal writes this database. A protected consumer must
independently verify sources, policy and remote state before admission.
"""
import hashlib,json,os,re,secrets,sqlite3,stat
from pathlib import Path
import github_proposals as P
import source_snapshot as S

def checked(value):
    S.require(type(value) is dict and set(value)=={'repository','repository_id','number','draft','head','base','branch'},'QUEUE_PROPOSAL_FIELDS')
    repository=value['repository'];S.require(repository in P.REPOSITORIES,'QUEUE_REPOSITORY_REFUSED')
    repo={'id':value['repository_id'],'full_name':'MrJ-am/'+repository}
    projected=P.project(repository,{'number':value['number'],'draft':value['draft'],'state':'open',
        'base':{'repo':repo,'ref':'main','sha':value['base']},
        'head':{'repo':repo,'ref':value['branch'],'sha':value['head']}})
    S.require(projected==value,'QUEUE_PROPOSAL_REFUSED')
    return value

def key(proposal):
    return hashlib.sha256(json.dumps(checked(proposal),sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Queue:
    def __init__(self,directory):
        self.directory=Path(directory)
        S.require(self.directory.is_absolute() and self.directory.resolve()==self.directory,'QUEUE_DIRECTORY_REFUSED')
        info=self.directory.lstat()
        S.require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'QUEUE_DIRECTORY_REFUSED')
        self.path=self.directory/'intake.sqlite'
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
        except FileExistsError:pass
        for path in (self.path,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')):
            if not path.exists() and not path.is_symlink():continue
            info=path.lstat()
            S.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
                and stat.S_IMODE(info.st_mode)==0o600,'QUEUE_FILE_REFUSED')
        self.db=sqlite3.connect(self.path,timeout=3,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            version=self.db.execute('PRAGMA user_version').fetchone()[0]
            S.require(version in (0,1),'QUEUE_VERSION_REFUSED')
            if version==0:
                self.db.execute('''CREATE TABLE jobs (
                    key TEXT PRIMARY KEY, proposal TEXT NOT NULL, visible INTEGER NOT NULL,
                    draft INTEGER NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    created INTEGER NOT NULL, updated INTEGER NOT NULL, next_attempt INTEGER NOT NULL,
                    lease TEXT, lease_until INTEGER, receipt TEXT, code TEXT)''')
                self.db.execute('PRAGMA user_version=1')
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');self.db.close();raise
    def close(self):self.db.close()
    def observe(self,proposals,now):
        S.require(type(now) is int and now>=0 and type(proposals) is list,'QUEUE_OBSERVATION_REFUSED')
        rows=[];seen=set()
        for proposal in proposals:
            checked(proposal);identity=(proposal['repository'],proposal['number'])
            S.require(identity not in seen,'QUEUE_DUPLICATE_OBSERVATION');seen.add(identity)
            rows.append((key(proposal),json.dumps(proposal,sort_keys=True),int(proposal['draft']),now,now,now))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('UPDATE jobs SET visible=0')
            self.db.executemany('''INSERT INTO jobs(key,proposal,visible,draft,state,created,updated,next_attempt)
                VALUES(?,?,1,?,'pending',?,?,?) ON CONFLICT(key) DO UPDATE SET visible=1''',rows)
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def claim(self,now,lease_seconds=900):
        S.require(type(now) is int and now>=0 and type(lease_seconds) is int and 1<=lease_seconds<=1800,'QUEUE_LEASE_REFUSED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("UPDATE jobs SET state='retry',lease=NULL,lease_until=NULL,next_attempt=?,code='INTAKE_INTERRUPTED' WHERE state='running' AND lease_until<=?",(now,now))
            row=self.db.execute("SELECT * FROM jobs WHERE visible=1 AND draft=0 AND state IN ('pending','retry') AND next_attempt<=? ORDER BY next_attempt,created,key LIMIT 1",(now,)).fetchone()
            if row is None:self.db.execute('COMMIT');return None
            proposal=checked(json.loads(row['proposal']));S.require(key(proposal)==row['key'],'QUEUE_CONTENT_REFUSED')
            lease=secrets.token_hex(16)
            self.db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated=?,lease=?,lease_until=? WHERE key=?",(now,lease,now+lease_seconds,row['key']))
            self.db.execute('COMMIT')
            return {'key':row['key'],'proposal':proposal,'lease':lease,'attempt':row['attempts']+1}
        except BaseException:self.db.execute('ROLLBACK');raise
    def finish(self,claim,now,*,receipt=None,code=None,retry_seconds=300):
        S.require(type(now) is int and now>=0 and type(retry_seconds) is int and 1<=retry_seconds<=86400,'QUEUE_COMPLETION_REFUSED')
        S.require((receipt is None)!=(code is None),'QUEUE_RESULT_REFUSED')
        if receipt is not None:S.require(type(receipt) is str and re.fullmatch('[0-9a-f]{64}',receipt),'QUEUE_RECEIPT_REFUSED')
        if code is not None:S.require(type(code) is str and re.fullmatch('[A-Z_]{1,80}',code),'QUEUE_CODE_REFUSED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT * FROM jobs WHERE key=?',(claim['key'],)).fetchone()
            S.require(row is not None and row['state']=='running' and row['lease']==claim['lease'] and row['lease_until']>now,'QUEUE_STALE_LEASE')
            self.db.execute('''UPDATE jobs SET state=?,receipt=?,code=?,updated=?,next_attempt=?,lease=NULL,lease_until=NULL WHERE key=?''',
                ('ready' if receipt is not None else 'retry',receipt,code,now,now+retry_seconds,claim['key']))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def ready(self):
        # Visibility is not authority: a PR may already have been merged or
        # closed. The consumer checks that independently, without losing work.
        return [dict(row) for row in self.db.execute("SELECT key,proposal,receipt,visible FROM jobs WHERE state='ready' ORDER BY created,key")]
    def acknowledge(self,job_key,receipt,now):
        S.require(type(now) is int and now>=0,'QUEUE_ACK_REFUSED')
        cursor=self.db.execute("UPDATE jobs SET state='consumed',updated=? WHERE key=? AND receipt=? AND state IN ('ready','consumed')",(now,job_key,receipt))
        S.require(cursor.rowcount==1,'QUEUE_ACK_REFUSED')
    def reprepare(self,job_key,receipt,now):
        """Discard readiness after the protected adopted base has advanced.

        Match the exact receipt, so an old controller cannot invalidate a
        newer preparation. This grants neither admission nor deployment.
        """
        S.require(type(now) is int and now>=0,'QUEUE_REPREPARE_REFUSED')
        cursor=self.db.execute("UPDATE jobs SET state='retry',receipt=NULL,code='ADOPTED_BASE_CHANGED',updated=?,next_attempt=? WHERE key=? AND receipt=? AND state='ready'",(now,now,job_key,receipt))
        S.require(cursor.rowcount==1,'QUEUE_REPREPARE_REFUSED')
