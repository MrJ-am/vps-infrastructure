"""Mirror an exact validated proposal; never update main or submit a review."""
import base64,http.client,json,re
import delivery_roles as R
import intake_queue as Q
import source_fetch as F
import source_snapshot as S

FORGE_IDS={'Signature':4,'apprendre-a-demontrer':5,'etp-vie-affective':6,
    'matheval':7,'mrjam-plateforme':8,'style-mrjam':10,'vision':11}

def branch_name(proposal):
    Q.checked(proposal)
    S.require(proposal['repository'] in FORGE_IDS and proposal['draft'] is False,'MIRROR_SCOPE_REFUSED')
    return 'cloud/pr-'+str(proposal['number'])+'-'+proposal['head']

def git_environment(token):
    # Reuse the no-hook/no-helper/no-redirect transport, replacing its only
    # authenticated origin. Never pass either token in argv, URL or output.
    env=F.environment(token)
    for index in range(int(env['GIT_CONFIG_COUNT'])):
        key='GIT_CONFIG_KEY_'+str(index)
        if env[key]=='http.https://github.com/.extraHeader':
            env[key]='http.https://forge.mrj.am/.extraHeader'
            env['GIT_CONFIG_VALUE_'+str(index)]='Authorization: Basic '+base64.b64encode(
                (R.ROLES['mirror']+':'+token).encode()).decode()
    return env

def transfer(directory,git,proposal,observed,github_credentials,forge_token,branch):
    S.require(branch==branch_name(proposal),'MIRROR_BRANCH_REFUSED')
    reader=F.receive(directory,git,proposal,github_credentials)
    tree,_=S.commit(reader,proposal['head'])
    S.require(observed=={'repository':'MrJ-am/'+proposal['repository'],
        'revision':proposal['head'],'tree_sha':tree},'MIRROR_TREE_REFUSED')
    F.execute([str(git),'--git-dir='+str(reader.repository),'push','--quiet','--no-verify',
        '--force-with-lease=refs/heads/'+branch+':','https://forge.mrj.am/MrJ-am/'+proposal['repository']+'.git',
        proposal['head']+':refs/heads/'+branch],git_environment(forge_token))

class API:
    def __init__(self,repository,branch,token,policy_token):
        S.require(repository in FORGE_IDS and re.fullmatch(r'cloud/pr-[1-9][0-9]*-[0-9a-f]{40}',branch),'MIRROR_API_SCOPE_REFUSED')
        self.repository=repository;self.branch=branch;self.token=token;self.policy_token=policy_token
    def __call__(self,method,suffix,body=None):
        allowed=(method=='GET' and body is None and (suffix in ('','/branches/main','/branch_protections/main',
            '/branches/'+self.branch) or re.fullmatch(r'/pulls\?state=all&limit=50&page=[1-9][0-9]?',suffix)))
        allowed=allowed or (method=='POST' and suffix=='/pulls' and type(body) is dict
            and set(body)=={'base','head','title','body'} and body['base']=='main' and body['head']==self.branch)
        S.require(allowed,'MIRROR_API_ROUTE_REFUSED')
        connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
        try:
            token=self.policy_token if method=='GET' and suffix=='/branch_protections/main' else self.token
            connection.request(method,'/api/v1/repos/MrJ-am/'+self.repository+suffix,
                body=None if body is None else json.dumps(body),headers={'Host':'forge.mrj.am',
                    'Authorization':'token '+token,'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(1048577)
            S.require(len(raw)<=1048576,'MIRROR_API_RESPONSE_LIMIT')
            if response.status==404 and method=='GET' and suffix=='/branches/'+self.branch:return None
            S.require(response.status in (200,201),'MIRROR_API_REFUSED')
            return json.loads(raw)
        finally:connection.close()

def mirror(proposal,digest,run_id,request,push):
    branch=branch_name(proposal);repository=proposal['repository']
    S.require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest)
        and type(run_id) is int and run_id>0,'MIRROR_VALIDATION_IDENTITY_REFUSED')
    repo=request('GET','')
    S.require(repo.get('id')==FORGE_IDS[repository] and repo.get('full_name')=='MrJ-am/'+repository
        and repo.get('private') is True and repo.get('has_actions') is False
        and repo.get('default_branch')=='main','MIRROR_REPOSITORY_REFUSED')
    protection=request('GET','/branch_protections/main')
    desired=R.protection_change(repository,protection)
    R.verify_protection(protection,protection,desired)
    def base():
        S.require(request('GET','/branches/main')['commit']['id']==proposal['base'],'MIRROR_BASE_MOVED')
    base()
    current=request('GET','/branches/'+branch)
    if current is None:
        push(branch)
        current=request('GET','/branches/'+branch)
    S.require(type(current) is dict and current.get('commit',{}).get('id')==proposal['head'],'MIRROR_BRANCH_COLLISION')
    base()
    matches=[]
    for page in range(1,100):
        rows=request('GET','/pulls?state=all&limit=50&page='+str(page))
        S.require(type(rows) is list and len(rows)<=50,'MIRROR_PULL_PAGE_REFUSED')
        for row in rows:
            if row.get('head',{}).get('ref')==branch:
                S.require(row['head'].get('sha')==proposal['head'] and row.get('base',{}).get('ref')=='main'
                    and row.get('user',{}).get('login')==R.ROLES['mirror'],'MIRROR_PULL_COLLISION')
                matches.append(row)
        if len(rows)<50:break
    else:S.require(False,'MIRROR_PULL_PAGINATION_LIMIT')
    S.require(len(matches)<=1,'MIRROR_DUPLICATE_PULL')
    if matches:
        pr=matches[0]
        S.require(pr.get('state')=='open' and pr.get('merged') is False,'MIRROR_PULL_ALREADY_CLOSED')
    else:
        pr=request('POST','/pulls',{'base':'main','head':branch,
            'title':'Proposition GitHub nº'+str(proposal['number'])+' — '+proposal['head'][:12],
            'body':'Source : https://github.com/MrJ-am/'+repository+'/pull/'+str(proposal['number'])+
                '\nCommit exact : '+proposal['head']+'\nProposition validée : '+digest+
                '\nValidation indépendante : https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/'+str(run_id)+
                '\nCette réception ne constitue ni une revue, ni une fusion, ni un déploiement.'})
    S.require(type(pr.get('number')) is int and pr['number']>0 and pr.get('head',{}).get('sha')==proposal['head']
        and pr.get('base',{}).get('ref')=='main' and pr.get('state')=='open' and pr.get('merged') is False
        and pr.get('user',{}).get('login')==R.ROLES['mirror'],'MIRROR_PULL_CONFIRMATION_REFUSED')
    base();S.require(request('GET','/branch_protections/main')==protection,'MIRROR_PROTECTION_CHANGED')
    return {'repository':repository,'repository_id':FORGE_IDS[repository],'number':pr['number'],
        'branch':branch,'head':proposal['head'],'base':proposal['base'],'proposal_sha256':digest,
        'author':R.ROLES['mirror'],'reviewed':False,'merged':False,'deployed':False}
