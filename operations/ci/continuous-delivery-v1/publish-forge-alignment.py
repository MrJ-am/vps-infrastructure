"""Mirror one verified private source branch and propose its protected merge."""
import base64,http.client,importlib.util,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
import contract as C
import admission_control as R
import signer as A
HEAD='5a05461e9e3eb7cf77e99b85ae8d49630f13004d'
BASE='2a34dac722ff1dab9a63aec56e407dd996de0719'
BRANCH='spectre/source-alignment-20261103'
DIGEST='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
PREFIX='/api/v1/repos/MrJ-am/mrjam-plateforme'
GIT='/run/current-system/sw/bin/git'

def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    policy=R.load(DIGEST)['authority']
    raw=C.regular_file(Path('/var/lib/mrjam-delivery-captures')/DIGEST/'attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT)
    C.require(A.verify(C.parse(raw),policy) and C.sha(raw)=='645cbd33f82d0be8dbc2eef6990ba854a3610d96476c83dc922265b7f46a1e01','ATTESTATION_REFUSED')
    C.require(any(s['revision']==HEAD and s['repository']=='MrJ-am/mrjam-plateforme' for s in policy['sources']),'SOURCE_REFUSED')
    env={'LANG':'C','HOME':'/nonexistent','PATH':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_NO_REPLACE_OBJECTS':'1','GIT_ALLOW_PROTOCOL':'https','GIT_SSL_CAINFO':'/etc/ssl/certs/ca-certificates.crt'}
    prefix=[GIT,'-c','core.hooksPath=/dev/null','--git-dir=/var/lib/mrjam-github-intake-bootstrap/candidate.git']
    def git(args):
        result=subprocess.run(prefix+args,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=120)
        C.require(result.returncode==0,'GIT_REFUSED');return result.stdout
    C.require(git(['rev-parse','refs/heads/'+BRANCH]).decode().strip()==HEAD,'LOCAL_HEAD_REFUSED')
    git(['merge-base','--is-ancestor',BASE,HEAD])
    paths=git(['ls-tree','-r','--name-only',HEAD]).decode().splitlines()
    C.require(not any(p.startswith(('.github/workflows/','.forgejo/workflows/','.gitea/workflows/')) for p in paths),'WORKFLOWS_REFUSED')
    spec=importlib.util.spec_from_file_location('bootstrap','/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1/libexec/core.py')
    B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
    with B.governance_lease() as token:
        def api(method,suffix,body=None,missing=False):
            c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
            c.request(method,PREFIX+suffix,body=None if body is None else json.dumps(body),headers={'Host':'forge.mrj.am','Authorization':'token '+token,'Content-Type':'application/json'})
            r=c.getresponse();data=r.read(1048577);status=r.status;c.close()
            C.require(len(data)<=1048576,'API_LIMIT')
            if missing and status==404:return None
            C.require(status in (200,201),'API_REFUSED');return json.loads(data)
        repo=api('GET','')
        C.require(repo['id']==8 and repo['private'] and not repo['has_actions'],'REPOSITORY_REFUSED')
        C.require(api('GET','/branches/main')['commit']['id']==BASE,'MAIN_MOVED')
        protection=api('GET','/branch_protections/main')
        C.require(protection['required_approvals']==1 and protection['enable_status_check'] and protection['status_check_contexts']==['mrjam/independent-validation'] and protection['apply_to_admins'],'PROTECTION_REFUSED')
        branch=api('GET','/branches/'+BRANCH,missing=True)
        if branch is None:
            settings={'credential.helper':'','http.proxy':'','http.followRedirects':'false','http.sslVerify':'true','http.extraHeader':'','http.https://forge.mrj.am/.extraHeader':'Authorization: Basic '+base64.b64encode(('mrjam-governance-bootstrap:'+token).encode()).decode(),'protocol.allow':'never','protocol.https.allow':'always'}
            env['GIT_CONFIG_COUNT']=str(len(settings))
            for i,(key,value) in enumerate(settings.items()):env['GIT_CONFIG_KEY_'+str(i)]=key;env['GIT_CONFIG_VALUE_'+str(i)]=value
            git(['push','--quiet','--no-verify','--force-with-lease=refs/heads/'+BRANCH+':','https://forge.mrj.am/MrJ-am/mrjam-plateforme.git',HEAD+':refs/heads/'+BRANCH])
            for key in list(env):
                if key.startswith('GIT_CONFIG_') and key not in ('GIT_CONFIG_NOSYSTEM','GIT_CONFIG_GLOBAL'):del env[key]
        C.require(api('GET','/branches/'+BRANCH)['commit']['id']==HEAD,'REMOTE_HEAD_REFUSED')
        rows=api('GET','/pulls?state=open&limit=50')
        matches=[p for p in rows if p['head']['ref']==BRANCH and p['head']['sha']==HEAD and p['base']['ref']=='main']
        C.require(len(rows)<50 and len(matches)<=1,'PULLS_REFUSED')
        if not matches:
            pr=api('POST','/pulls',{'base':'main','head':BRANCH,'title':'Réconcilier les sources et qualifier le workspace Rust/Elm','body':'Préserve les historiques et intègre la disponibilité dans les sources. Tête exacte : '+HEAD+'. Validation indépendante Forgejo nº2 : 74 contrôles réussis, signature Ed25519 et artefacts vérifiés. Cette proposition ne modifie aucun workflow ; elle reste soumise à la revue et aux protections de main. Aucune livraison effectuée.'})
        else:pr=matches[0]
        api('POST','/statuses/'+HEAD,{'state':'success','context':'mrjam/independent-validation','description':'74 contrôles réussis ; attestation Ed25519 vérifiée','target_url':'https://forge.mrj.am/MrJ-am/mrjam-validation/actions/runs/2'})
        C.require(api('GET','/branches/main')['commit']['id']==BASE and api('GET','/branch_protections/main')==protection,'MAIN_OR_PROTECTION_CHANGED')
    print(json.dumps({'code':'PROTECTED_SOURCE_REVIEW_READY','number':pr['number'],'url':pr['html_url'],'head':HEAD,'main_unchanged':True,'protection_unchanged':True,'temporary_token_revoked':True,'merged':False,'deployed':False}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':str(error) if isinstance(error,C.Refused) else 'FORGE_ALIGNMENT_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
