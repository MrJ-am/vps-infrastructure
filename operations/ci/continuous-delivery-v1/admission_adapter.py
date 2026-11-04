"""Concrete protected operations used by the persistent admission controller.

Paths and executables are installed configuration. Credentials remain inside
this process and its fixed API clients; neither Git source nor candidate code
executes here. Actual compilation belongs to the isolated CI worker.
"""
import http.client,json,os,re,shutil,stat,subprocess
from pathlib import Path
import github_proposals as P
import intake_capture as I
import intake_prepare as W
import proposal_policy as V
import source_observation as S
import validation_dispatch as D
import validation_feedback as F
import delivery_capture as DC
from proposal_prepare import encode,sha
from source_snapshot import require

ANCHOR='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'
STORE=re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]{1,100}\Z')
HEX=re.compile('[0-9a-f]{64}\\Z')

class Adapter:
    def __init__(self,*,adopted_path,state,decisions,recipe,nix_build,credentials,forge_token,
                 validator_policy,gate_path,contract,registry,control,signer,stager,
                 profile='platform',anchor_control=ANCHOR,staging_catalog=None):
        require(profile in {'platform','vise-v1'} and STORE.fullmatch(anchor_control),'ADAPTER_PROFILE_REFUSED')
        self.profile=profile;self.anchor_control=anchor_control
        self.staging_catalog=staging_catalog
        self.adopted_path=Path(adopted_path);self.state=Path(state);self.inbox=Path(decisions)
        self.recipe=Path(recipe);self.nix_build=nix_build;self.credentials=credentials;self.forge_token=forge_token
        self.policy=validator_policy;self.gate_path=gate_path
        self.C=contract;self.R=registry;self.A=control;self.signer=signer;self.stager=stager
        self.owner=self.state.lstat().st_uid
    def adopted(self):
        descriptor=self.adopted_path.resolve(strict=True)
        require(STORE.fullmatch(str(descriptor)),'ADOPTED_STORE_PATH_REFUSED')
        value=self.C.parse(self.R.store_bytes(str(descriptor),65536))
        self.C.exact(value,{'schema_version','source','policy','proposal_sha256'})
        require(value['schema_version']==1 and HEX.fullmatch(value['proposal_sha256']),'ADOPTED_DESCRIPTOR_REFUSED')
        for field in ('source','policy'):require(STORE.fullmatch(value[field]),'ADOPTED_STORE_PATH_REFUSED')
        raw=self.R.store_bytes(value['policy'])
        policy=self.policy.checked_policy(self.C.parse(raw))
        return value,policy,sha(encode(policy))
    def check_ready(self,item):
        self.C.exact(item,{'job','result','base_sha256','base_policy_sha256'})
        for field in ('result','base_sha256','base_policy_sha256'):self.C.text(item[field],HEX)
        job=item['job'];self.C.exact(job,{'key','proposal','receipt','visible'})
        self.C.text(job['key'],HEX);self.C.text(job['receipt'],HEX)
        require(type(job['proposal']) is str and len(job['proposal'])<=4096,'READY_PROPOSAL_LIMIT')
        proposal=W.Q.checked(self.C.parse(job['proposal'].encode(),4096))
        require(W.Q.key(proposal)==job['key'] and proposal['draft'] is False
            and type(job['visible']) is int and job['visible'] in (0,1),'READY_JOB_REFUSED')
    def current(self,value):
        adopted,_,policy_sha=self.adopted();ready=value['ready']
        return adopted['proposal_sha256']==ready['base_sha256'] and policy_sha==ready['base_policy_sha256']
    def observe(self,value):
        require(self.current(value),'ADOPTED_BASE_CHANGED')
        capture=value['capture'];observed=S.observe(capture['proposal'],self.credentials)
        require(all(binding==observed for binding in capture['observed'].values()),'PROPOSAL_OBSERVATION_CHANGED')
    def capture(self,path,value):
        adopted,policy,_=self.adopted();destination=path/'capture'
        observe=lambda proposal:S.observe(proposal,self.credentials)
        self.recover_partial(destination)
        if not destination.exists():
            return I.capture(self.state/'prepared',destination,value['ready']['job'],adopted['proposal_sha256'],policy,
                intake_uid=self.owner,validator_policy=self.policy,gate_path=self.gate_path,
                observe=observe,still_adopted=lambda:self.current(value))
        # A prior copy may have completed before its journal transition. Its
        # private bytes and policy are rechecked against a new API observation.
        W.private_directory(destination)
        captured=self.C.parse(W.read_file(destination/'capture.json',65536))
        require(captured['job_key']==value['ready']['job']['key']
            and captured['intake_receipt_sha256']==value['ready']['job']['receipt']
            and captured['base_sha256']==adopted['proposal_sha256']
            and captured['base_policy_sha256']==value['ready']['base_policy_sha256'],'CAPTURE_RECOVERY_BINDING')
        proposed_raw=W.read_file(destination/'policy.json',1048576)
        require(sha(proposed_raw)==captured['policy_sha256'],'CAPTURE_RECOVERY_POLICY')
        fresh=observe(captured['proposal'])
        observed={s['id']:fresh for s in policy['sources'] if s['repository']==fresh['repository']}
        V.verify(destination/'source',policy,self.C.parse(proposed_raw),observed,captured['proposal_sha256'],
            validator_policy=self.policy,gate_path=self.gate_path)
        require(observed==captured['observed'] and self.current(value),'CAPTURE_RECOVERY_OBSERVATION')
        return captured
    def execute(self,args,timeout=600):
        process=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            timeout=timeout,env={'PATH':'/nonexistent','HOME':os.environ.get('STATE_DIRECTORY','/var/empty'),'LANG':'C','LC_ALL':'C'})
        require(process.returncode==0 and len(process.stdout)<=65536,'CONTROLLER_OPERATION_FAILED')
        return process.stdout
    def construct(self,path,value):
        require(self.current(value),'ADOPTED_BASE_CHANGED')
        validity=value['validity']
        expression=('operations/vise/delivery/captured-admission.nix' if self.profile=='vise-v1'
                    else 'operations/ci/continuous-delivery-v1/captured-admission.nix')
        anchor_args=(['--argstr','anchorControl',self.anchor_control]
                     if self.profile=='vise-v1' or self.anchor_control!=ANCHOR else [])
        packages=('/nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source' if self.profile=='vise-v1'
                  else '/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source')
        raw=self.execute([self.nix_build,str(self.recipe/expression),
            '--arg','pkgs','import '+packages+' { system = "x86_64-linux"; config = {}; overlays = []; }',
            '--argstr','captureRoot',str(path/'capture'),'--arg','notBefore',str(validity['not_before']),
            '--arg','expiresAt',str(validity['expires_at']),'--out-link',str(path/'bundle'),
            '--option','builders','','--max-jobs','1','--cores','2',*anchor_args])
        bundle=raw.decode('ascii').strip();require(STORE.fullmatch(bundle),'CONSTRUCTOR_RESULT_REFUSED')
        self.bundle(bundle,path,value)
        return bundle
    def bundle(self,bundle,path,value):
        require(type(bundle) is str and STORE.fullmatch(bundle),'CONSTRUCTOR_RESULT_REFUSED')
        descriptor=Path(bundle,'descriptor.json').resolve(strict=True)
        require(STORE.fullmatch(str(descriptor)),'CONSTRUCTOR_DESCRIPTOR_REFUSED')
        data=self.C.parse(self.R.store_bytes(str(descriptor)))
        self.C.exact(data,{'schema_version','proposal_sha256','capture_sha256','source','validator','verifierNarHash',
            'control','publisher','record','metadata','anchor_control'})
        require(data['schema_version']==1 and data['anchor_control']==self.anchor_control
            and data['proposal_sha256']==value['capture']['proposal_sha256']
            and data['capture_sha256']==sha(W.read_file(path/'capture/capture.json',65536)),'CONSTRUCTOR_CAPTURE_BINDING')
        for field in ('source','validator','control','publisher','record','metadata'):require(STORE.fullmatch(data[field]),'CONSTRUCTOR_STORE_REFUSED')
        record=self.C.parse(self.R.store_bytes(data['record'],16384))
        if self.profile=='platform':
            anchor=self.C.parse(self.R.store_bytes(self.A.ANCHOR_PATH))
            selected=self.R.resolve(record,data['proposal_sha256'],anchor,self.A.BUBBLEWRAP)
        else:
            anchor=self.A.anchor_for('vise-v1')
            selected=self.R.resolve(record,data['proposal_sha256'],anchor,self.A.BUBBLEWRAP,profile='vise-v1')
        require(selected['authority']['report_policy_sha256']==value['capture']['policy_sha256']
            and selected['authority']['not_before']==value['validity']['not_before']
            and selected['authority']['expires_at']==value['validity']['expires_at'],'CONSTRUCTOR_POLICY_BINDING')
        return data
    def admit(self,path,value):
        data=self.bundle(value['bundle'],path,value);adopted,policy,_=self.adopted()
        require(self.current(value),'ADOPTED_BASE_CHANGED')
        self.run_boundary(value)  # Do not replace inputs belonging to queued CI.
        # Retain the adopted source and this job while the worker is idle.
        proposals={adopted['proposal_sha256']:adopted['source'],data['proposal_sha256']:data['source']}
        configuration=({'schema_version':1,'rules_revision':policy['rules_revision'],
            'proposals':[{'sha256':digest,'source_store':source} for digest,source in proposals.items()]}
            if self.staging_catalog is None else self.staging_catalog(value,data))
        self.stager.reconcile(configuration)
        response=self.C.parse(self.execute([data['publisher']+'/bin/mrjam-publish-fixed-admission'],timeout=60))
        require(response['code']=='FIXED_ADMISSION_PUBLISHED' and response['proposal_sha256']==data['proposal_sha256'],'ADMISSION_PUBLICATION_REFUSED')
        self.A.load(data['proposal_sha256'])
    def request(self,method,path,body=None):
        get_paths=(r'/branches/main',r'/actions/runs\?limit=50&page=[1-9][0-9]{0,2}',r'/actions/runs/[1-9][0-9]{0,9}',
            r'/contents/\.forgejo/workflows/independent-validation\.yml\?ref=[0-9a-f]{40}')
        suffix=path.removeprefix(D.BASE)
        require(path.startswith(D.BASE) and ((method=='GET' and body is None and any(re.fullmatch(p,suffix) for p in get_paths))
            or (method=='POST' and suffix=='/actions/workflows/independent-validation.yml/dispatches')),'FORGE_ENDPOINT_REFUSED')
        if method=='POST':
            self.C.exact(body,{'ref','inputs','return_run_info'});self.C.exact(body['inputs'],{'proposal_digest'})
            require(body['ref']=='main' and body['return_run_info'] is True,'FORGE_DISPATCH_REFUSED')
            self.C.text(body['inputs']['proposal_digest'],HEX)
        connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
        try:
            connection.request(method,path,body=None if body is None else json.dumps(body),
                headers={'Host':'forge.mrj.am','Authorization':'token '+self.forge_token,'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(1048577)
            require(response.status in (200,201,204) and len(raw)<=1048576,'FORGE_API_REFUSED')
            return self.C.parse(raw,1048576) if raw else None
        finally:connection.close()
    def run_boundary(self,value):
        response=self.request('GET',D.BASE+'/actions/runs?limit=50&page=1');rows=response.get('workflow_runs')
        require(type(rows) is list and len(rows)<=50 and all(type(row) is dict and row.get('status') in D.TERMINAL
            and type(row.get('id')) is int and row['id']>0 for row in rows),'CI_BUSY')
        return max((row['id'] for row in rows),default=0)
    def dispatch(self,value):
        capture=value['capture'];policy=self.A.load(capture['proposal_sha256'])['authority']
        return D.ensure(self.request,capture['proposal_sha256'],policy['rules_revision'],after_id=value['after_id'])
    def poll(self,value):
        policy=self.A.load(value['capture']['proposal_sha256'])['authority'];identifier=value['run']['id']
        row=self.request('GET',D.BASE+'/actions/runs/'+str(identifier))
        require(row.get('id')==identifier,'VALIDATION_RUN_CHANGED')
        result=D.identify(row,value['capture']['proposal_sha256'],policy['rules_revision'])
        require(result is not None,'VALIDATION_RUN_BINDING_REFUSED');return result
    def capture_artifacts(self,path,value):
        proposal=value['capture']['proposal_sha256'];policy=self.A.load(proposal)['authority'];destination=path/'artifacts'
        self.recover_partial(destination)
        if not destination.exists():
            return DC.capture(proposal,policy,destination,attestations='/var/lib/mrjam-forgejo-runner/attestations',
                cache='/var/lib/mrjam-validation-collector/authority-v1/artifacts',contract=self.C,verify=self.signer.verify)
        W.private_directory(destination)
        envelope=self.C.parse(W.read_file(destination/'attestation.json',self.C.MAX_DOCUMENT))
        require(self.signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==proposal,'CAPTURED_SIGNATURE_REFUSED')
        result=self.C.parse(W.read_file(destination/'capture.json',self.C.MAX_DOCUMENT))
        require(result['proposal_sha256']==proposal and result['artifacts']==envelope['payload']['artifacts'],'CAPTURED_ARTIFACT_BINDING')
        for item in result['artifacts']:
            raw=W.read_file(destination/item['name'],dict(self.C.ARTIFACTS)[item['name']])
            require(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'CAPTURED_ARTIFACT_CHANGED')
        return result
    def feedback(self,path,value):
        # Do not trust a journal boolean or the forge's green result alone.
        # Reverify signature and every captured artifact before publication.
        self.capture_artifacts(path,value)
        run=self.poll(value)
        policy=self.A.load(value['capture']['proposal_sha256'])['authority']
        envelope=self.C.parse(W.read_file(path/'artifacts/attestation.json',self.C.MAX_DOCUMENT))
        return F.publish(value['capture']['proposal'],run,policy,envelope,self.credentials,
            verify=self.signer.verify)
    def recover_partial(self,destination):
        if destination.exists() and not (destination/'capture.json').exists():
            W.private_directory(destination)
            require(shutil.rmtree.avoids_symlink_attacks,'SAFE_CAPTURE_RECOVERY_REQUIRED')
            shutil.rmtree(destination);W.sync_directory(destination.parent)
    def decision(self,value,action):
        require(action in {'captured','reprepare'},'DECISION_ACTION_REFUSED')
        job=value['ready']['job'];raw=encode({'schema_version':1,'key':job['key'],'receipt':job['receipt'],'action':action})
        self.inbox.mkdir(mode=0o755,exist_ok=True)
        info=self.inbox.lstat();require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o755,'DECISION_DIRECTORY_REFUSED')
        target=self.inbox/(job['key']+'-'+job['receipt']+'.json')
        if target.exists():
            require(self.R.store_bytes(str(target),4096)==raw,'DECISION_CONFLICT');return
        temporary=target.with_suffix('.next')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fchmod(output.fileno(),0o444);os.fsync(output.fileno())
        os.replace(temporary,target);W.sync_directory(self.inbox)
