"""Initial rules bootstrap only; no CI attestation, status or activation."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

import core as proposal
import credentials
import lease
import protection
import identity
import merge_transport
import api_projection as A
import review_contract as R
import read_transport_v2

TEXT="J’approuve l’amorçage initial du workflow, sur la base des vérifications hors CI décrites dans cette proposition."
ROOT='/api/v1/repos/MrJ-am/mrjam-validation'
PULL=ROOT+'/pulls/1'


class Refused(RuntimeError):
    pass


def require(value,code):
    if not value:raise Refused(code)


def normalized_body(value):
    require(type(value) is str and len(value.encode())<=8192,'HUMAN_REVIEW_REFUSED')
    return value.replace('\r\n','\n').strip()


def select_review(rows,owner,author,head,now):
    require(type(rows) is list and 1<=len(rows)<=10000,'HUMAN_REVIEW_REQUIRED')
    latest={}
    for row in sorted(rows,key=lambda r:r['id']):
        require(row['state'] in R.REVIEW_STATES and all(type(row[k]) is bool for k in ('official','stale','dismissed')),
                'REVIEW_SHAPE_REFUSED')
        require(type(row['updated_at']) is int and 0<=row['updated_at']<=now,'REVIEW_TIME_REFUSED')
        if row['state'] in ('APPROVED','REQUEST_CHANGES','REQUEST_REVIEW') and row['dismissed'] is False:
            latest[row['reviewer_id']]=row
    for row in latest.values():
        require(row['dismissed'] or row['state'] not in ('REQUEST_CHANGES','REQUEST_REVIEW'),'REVIEW_REQUEST_UNRESOLVED')
    row=latest.get(owner)
    require(owner!=author and row is not None and row['state']=='APPROVED' and row['official'] is True
        and row['stale'] is False and row['dismissed'] is False and row['commit_id']==head
        and normalized_body(row['body'])==TEXT,'HUMAN_REVIEW_REQUIRED')
    return row|{'body':normalized_body(row['body'])}


def reviews(api):
    result=[];seen=set();count=None
    for page in range(1,202):
        rows,headers=api.get(PULL+'/reviews?limit=50&page='+str(page))
        require(type(rows) is list and len(rows)<=50,'REVIEW_PAGE_REFUSED')
        total=headers.get('x-total-count')
        require(type(total) is str and re.fullmatch(r'0|[1-9][0-9]{0,4}',total),'REVIEW_COUNT_REFUSED')
        total=int(total)
        require(total<=10000 and (count is None or count==total),'REVIEW_COUNT_CHANGED');count=total
        for raw in rows:
            row=A.review_projection(raw)
            require(row['id'] not in seen,'DUPLICATE_REVIEW_PAGE');seen.add(row['id']);result.append(row)
        require(len(result)<=count,'REVIEW_COUNT_REFUSED')
        if len(result)==count:return result
        require(len(rows)==50,'INCOMPLETE_REVIEW_PAGE')
    raise Refused('REVIEW_PAGE_LIMIT')


def verify_review_participants(requested,rows):
    # Forgejo17 GetReviewsByIssueID includes approvals as well as requests and
    # rejections, excluding dismissed and comment/pending reviews. This field
    # is not a list of unresolved requests; those are checked by select_review.
    expected=sorted({row['reviewer_id'] for row in rows
        if row['state'] in ('APPROVED','REQUEST_CHANGES','REQUEST_REVIEW') and row['dismissed'] is False})
    require(requested==expected,'REVIEW_PARTICIPANTS_CHANGED')


def references(git,binding,merged=False):
    raw=git.command(['ls-remote','--refs','--heads','--tags',proposal.URL])
    result={}
    for line in raw.decode('ascii').splitlines():
        oid,sep,ref=line.partition('\t')
        require(sep and re.fullmatch(r'[0-9a-f]{40}',oid) and ref.startswith(('refs/heads/','refs/tags/'))
            and ref not in result,'REFERENCE_SHAPE_REFUSED');result[ref]=oid
    require(result.get('refs/heads/main')==binding.value['head' if merged else 'base']
        and result.get(binding.ref)==binding.value['head'],'REFERENCE_STATE_REFUSED')
    return result


def verify_source(git,binding,raw):
    # All operations here are local verification or fetch; there is no push.
    with tempfile.TemporaryDirectory(prefix='private-adoption-',dir=proposal.STATE) as root:
        path=str(Path(root)/'objects.git');bundle=Path(root)/'proposal.bundle'
        bundle.write_bytes(raw);bundle.chmod(0o600)
        git.command(['init','--bare','--initial-branch=main',path])
        git.command(['-C',path,'fetch','--depth=2','--no-tags','--no-recurse-submodules',proposal.URL,
            'refs/heads/main:refs/heads/base'])
        git.command(['-C',path,'bundle','verify',str(bundle)])
        git.command(['-C',path,'fetch','--no-tags','--no-recurse-submodules',str(bundle),binding.ref+':refs/heads/proposal'])
        head,base=binding.value['head'],binding.value['base']
        require(git.command(['-C',path,'rev-list','--parents','-n','1',head]).strip()==(head+' '+base).encode(),'PROPOSAL_PARENT_REFUSED')
        require(git.command(['-C',path,'rev-parse',head+'^{tree}']).strip()==binding.value['tree'].encode(),'PROPOSAL_TREE_REFUSED')
        require(git.command(['-C',path,'diff-tree','--no-commit-id','--name-status','-r','--no-renames','-z',base,head])
                ==b'A\0'+proposal.WORKFLOW.encode()+b'\0','PROPOSAL_DELTA_REFUSED')
        require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t'+re.escape(proposal.WORKFLOW.encode())+rb'\x00',
            git.command(['-C',path,'ls-tree','-z',head,'--',proposal.WORKFLOW])),'WORKFLOW_MODE_REFUSED')
        require(hashlib.sha256(git.command(['-C',path,'show',head+':'+proposal.WORKFLOW])).hexdigest()
            ==binding.value['workflow_sha256'],'WORKFLOW_BYTES_REFUSED')


def observe(api,binding,bootstrap,*,merged=False):
    owner=identity.owner(bootstrap)
    version,_=api.get('/api/v1/version');require(version=={'version':'17.0.1'},'FORGEJO_VERSION_REFUSED')
    me,_=api.get('/api/v1/user')
    require(type(me) is dict and type(me.get('id')) is int and me['id']>0
        and me.get('login')==lease.ACCOUNT and me.get('is_admin') is True and me['id']!=owner,'AUTHOR_IDENTITY_REFUSED')
    repo,_=api.get(ROOT)
    require(type(repo) is dict and type(repo.get('id')) is int and repo['id']>0
        and repo.get('full_name')=='MrJ-am/mrjam-validation' and repo.get('private') is True
        and repo.get('empty') is False and repo.get('archived') is False and repo.get('mirror') is False
        and repo.get('default_branch')=='main' and repo.get('has_actions') is False
        and repo.get('allow_fast_forward_only_merge') is True,'REPOSITORY_STATE_REFUSED')
    require(protection.verify(bootstrap),'MAIN_PROTECTION_REFUSED')
    raw,_=api.get(PULL);pull=A.pull_projection(raw,{'repository_id':repo['id']})
    require(raw.get('title')==proposal.TITLE and raw.get('body')==binding.body and raw['user']['id']==me['id']
        and pull['pull_request']==1 and pull['author_id']==me['id'] and pull['draft'] is False
        and pull['base_ref']=='main' and pull['head_sha']==binding.value['head']
        and raw['head']['ref']==binding.branch,'PULL_REQUEST_REFUSED')
    if merged:
        require(pull['state']=='closed' and pull['merged'] is True and raw.get('merge_commit_sha')==binding.value['head']
            and type(raw.get('merged_by')) is dict and raw['merged_by'].get('id')==me['id'],'MERGE_RESULT_REFUSED')
    else:
        require(pull['state']=='open' and pull['merged'] is False and pull['base_sha']==binding.value['base']
            and pull['merge_base']==binding.value['base'],'PULL_REQUEST_STATE_REFUSED')
    commit,_=api.get(ROOT+'/git/commits/'+binding.value['head']+'?stat=false&verification=false&files=false')
    # Forgejo17's commit.tree.sha is the commit ID, not the Git tree OID.
    # The native Git verification above the mutation binds the actual tree,
    # parent, exact diff and workflow bytes; do not reinterpret this API field.
    require(commit.get('sha')==binding.value['head'],'PROPOSAL_COMMIT_REFUSED')
    rows=reviews(api)
    verify_review_participants(pull['requested_reviewer_ids'],rows)
    chosen=select_review(rows,owner,me['id'],binding.value['head'],int(time.time()))
    again,_=api.get(PULL)
    require(A.pull_projection(again,{'repository_id':repo['id']})==pull and again.get('body')==binding.body
        and again.get('title')==proposal.TITLE,'PULL_REQUEST_CHANGED')
    one,_=api.get(PULL+'/reviews/'+str(chosen['id']));one=A.review_projection(one)
    one=one|{'body':normalized_body(one['body'])}
    require(one==chosen,'SELECTED_REVIEW_CHANGED')
    branch,_=api.get(ROOT+'/branches/main')
    require(branch['commit']['id']==binding.value['head' if merged else 'base'],'MAIN_CHANGED')
    return {'repository_id':repo['id'],'author_id':me['id'],'owner_id':owner,'review':chosen}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class Journal:
    NAME='bootstrap-adoption.json'
    def __init__(self,bootstrap,binding):
        self.bootstrap=bootstrap;self.binding=binding
        self.path=proposal.STATE/self.NAME;self.current=None
        try:raw=bootstrap.private_file(self.path,maximum=8192)
        except FileNotFoundError:return
        value=bootstrap.parse(raw)
        require(type(value) is dict and set(value)=={'schema_version','scope','binding_sha256','phase',
            'before_refs_sha256','before_refs_count','observation_sha256','review_id','owner_id','author_id',
            'repository_id','review_updated_at'},'ADOPTION_JOURNAL_REFUSED')
        require(type(value['schema_version']) is int and value['schema_version']==1
            and value['scope']=='mrjam-rules-bootstrap-adoption-v1'
            and value['binding_sha256']==digest(binding.value)
            and value['phase'] in ('prepared','merge-requested','merge-held','merged-reviewed')
            and type(value['before_refs_count']) is int and 2<=value['before_refs_count']<=100000
            and all(type(value[k]) is str and re.fullmatch(r'[0-9a-f]{64}',value[k])
                    for k in ('before_refs_sha256','observation_sha256'))
            and all(type(value[k]) is int and 1<=value[k]<=2**63-1
                    for k in ('review_id','owner_id','author_id','repository_id','review_updated_at')),
                    'ADOPTION_JOURNAL_REFUSED')
        self.current=value

    def write(self,phase,refs=None,observed=None):
        if self.current is None:
            require(phase=='prepared' and refs is not None and observed is not None,'ADOPTION_PHASE_REFUSED')
            value={'schema_version':1,'scope':'mrjam-rules-bootstrap-adoption-v1',
                'binding_sha256':digest(self.binding.value),'phase':phase,'before_refs_sha256':digest(refs),
                'before_refs_count':len(refs),'observation_sha256':digest(observed),
                'review_id':observed['review']['id'],'owner_id':observed['owner_id'],
                'author_id':observed['author_id'],'repository_id':observed['repository_id'],
                'review_updated_at':observed['review']['updated_at']}
        else:
            allowed={'prepared':('merge-requested',),'merge-requested':('merge-held','merged-reviewed'),
                     'merged-reviewed':('merge-held','merged-reviewed'),'merge-held':()}
            require(phase in allowed[self.current['phase']],'ADOPTION_PHASE_REFUSED')
            value=self.current|{'phase':phase}
        raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
        fd,temporary=tempfile.mkstemp(prefix='.bootstrap-adoption-',suffix='.next',dir=proposal.STATE)
        try:
            try:
                require(os.write(fd,raw)==len(raw),'ADOPTION_JOURNAL_WRITE_REFUSED');os.fsync(fd)
            finally:os.close(fd)
            os.replace(temporary,self.path)
        finally:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
        fd=os.open(proposal.STATE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.current=value


def adopt(binding,git,bootstrap,*,journal_factory=Journal,reader_factory=read_transport_v2.Transport,merge=merge_transport.merge):
    raw=proposal.private_bundle(binding,bootstrap.private_file)
    journal=journal_factory(bootstrap,binding)
    require(journal.current is None or journal.current['phase']!='merge-held','RULES_BOOTSTRAP_HELD')
    with lease.repository_lease(bootstrap) as token:
        with credentials.broker(token,proposal.REPO):
            def reader():return reader_factory(token,proposal.REPO,1)
            if journal.current is None or journal.current['phase']=='prepared':
                before=observe(reader(),binding,bootstrap)
                refs=references(git,binding)
                verify_source(git,binding,raw)
                fresh=observe(reader(),binding,bootstrap)
                require(fresh==before and references(git,binding)==refs,'PREMERGE_OBSERVATION_CHANGED')
                if journal.current is None:journal.write('prepared',refs,before)
                else:
                    require(journal.current['before_refs_sha256']==digest(refs)
                        and journal.current['before_refs_count']==len(refs)
                        and journal.current['observation_sha256']==digest(fresh),'PREMERGE_OBSERVATION_CHANGED')
                journal.write('merge-requested')
                try:merge(token,binding.value['head'])
                except merge_transport.Refused:
                    # A lost response is not a proof of either failure or
                    # success. Only a full post-merge observation can decide.
                    pass
            try:
                after=observe(reader(),binding,bootstrap,merged=True)
                refs_after=references(git,binding,merged=True)
                reconstructed=refs_after|{'refs/heads/main':binding.value['base']}
                require(journal.current['before_refs_sha256']==digest(reconstructed)
                    and journal.current['before_refs_count']==len(reconstructed)
                    and journal.current['observation_sha256']==digest(after),'POSTMERGE_OBSERVATION_CHANGED')
            except Exception:
                # Never undo a Git merge and never issue a CI/activation
                # decision after a revoked review, drift or ambiguous result.
                journal.write('merge-held')
                raise Refused('RULES_BOOTSTRAP_HELD') from None
            journal.write('merged-reviewed')
    return {'schema_version':1,'code':'RULES_BOOTSTRAP_MERGED_REVIEW_RECHECKED',
        'head':binding.value['head'],'tree':binding.value['tree'],'pull_request':1,
        'temporary_token_revoked':True,'main_fast_forward_observed':True,'other_heads_tags_unchanged':True,
        'protection_changed':False,'status_created':False,'review_created':False,
        'ci_attestation_issued':False,'activation_performed':False}
