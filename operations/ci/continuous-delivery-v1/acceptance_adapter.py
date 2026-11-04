"""Fixed adapters for separate reception, review, merge and synchronization roles."""
import http.client,json,tempfile
from pathlib import Path
import contract as C,admission_control as A,signer
import github_proposals as G,intake_queue as Q,source_observation as S
import validation_dispatch as D,forge_proposal as M,forge_review as V,forge_merge as F
import github_accepted_main as H
import delivery_profiles as Profiles

class Adapter:
    def __init__(self,stage,github,observer,role_token=None,git=None,commit=None,staged=None,*,enable_vise=False):
        C.require(stage in {'mirror','review','merge','sync'},'ACCEPTANCE_ROLE_REFUSED')
        C.require((stage=='sync' and role_token is None) or (stage!='sync' and type(role_token) is str and bool(role_token)),
            'ACCEPTANCE_CREDENTIAL_ROLE_REFUSED')
        self.stage=stage;self.github=github;self.observer=observer;self.token=role_token;self.git=git;self.commit=commit
        self.staged=staged
        C.require(type(enable_vise) is bool,'ACCEPTANCE_PROFILE_CONFIG_REFUSED')
        self.enable_vise=enable_vise
    def verified(self,directory,job):
        proposal=Q.checked(job['capture']['proposal']);digest=job['capture']['proposal_sha256']
        profile=Profiles.selected(proposal)
        C.require(profile=='platform' or self.enable_vise,'ACCEPTANCE_PROFILE_NOT_INSTALLED')
        adopted_path=('/etc/mrjam-vise-delivery-adopted.json' if profile=='vise'
                      else '/etc/mrjam-delivery-adopted.json')
        adopted=C.parse(Path(adopted_path).read_bytes())
        C.require(adopted['proposal_sha256']==job['ready']['base_sha256'],'ACCEPTANCE_ADOPTED_BASE_CHANGED')
        policy=A.load(digest)['authority']
        envelope=C.parse(C.regular_file(directory/'artifacts/attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT))
        C.require(signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==digest,'ACCEPTANCE_SIGNATURE_REFUSED')
        for item in envelope['payload']['artifacts']:
            raw=C.regular_file(directory/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
            C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'ACCEPTANCE_CAPTURE_CHANGED')
        sources={(s['repository'],s['revision'],s['tree_sha']) for s in policy['sources']
            if s['repository']=='MrJ-am/'+proposal['repository'] and s['revision']==proposal['head']}
        C.require(len(sources)==1,'ACCEPTANCE_SOURCE_BINDING_REFUSED')
        expected=dict(zip(['repository','revision','tree_sha'],next(iter(sources))))
        identifier=job['run']['id'];C.require(type(identifier) is int and identifier>0,'ACCEPTANCE_RUN_ID_REFUSED')
        connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
        try:
            connection.request('GET',D.BASE+'/actions/runs/'+str(identifier),headers={
                'Host':'forge.mrj.am','Authorization':'token '+self.observer})
            response=connection.getresponse();raw=response.read(1048577)
            C.require(response.status==200 and len(raw)<=1048576,'ACCEPTANCE_RUN_OBSERVATION_REFUSED');row=json.loads(raw)
        finally:connection.close()
        C.require(row.get('id')==identifier,'ACCEPTANCE_RUN_CHANGED')
        run=D.identify(row,digest,policy['rules_revision'])
        C.require(run is not None and run['terminal'] is True and run['status']=='success','ACCEPTANCE_RUN_NOT_SUCCESSFUL')
        return proposal,policy,envelope,run,expected
    def execute(self,stage,directory,job,receipts):
        C.require(stage==self.stage,'ACCEPTANCE_SERVICE_STAGE_REFUSED')
        proposal,policy,envelope,run,expected=self.verified(directory,job)
        def observe():C.require(S.observe(proposal,self.github)==expected,'ACCEPTANCE_REMOTE_SOURCE_CHANGED')
        digest=job['capture']['proposal_sha256']
        if stage=='mirror':
            observe()
            api=M.API(proposal['repository'],M.branch_name(proposal),self.token,self.observer)
            with tempfile.TemporaryDirectory(prefix='mrjam-acceptance-',dir='/tmp') as temporary:
                return M.mirror(proposal,digest,run['id'],api,lambda branch:M.transfer(
                    temporary,self.git,proposal,expected,self.github,self.token,branch))
        reception=receipts['mirror'];number=reception['number']
        C.require(reception['head']==proposal['head'] and reception['repository']==proposal['repository']
            and reception['proposal_sha256']==digest,'ACCEPTANCE_RECEPTION_CHANGED')
        if stage=='review':
            observe();api=V.API(proposal,number,self.token,self.observer)
            return V.approve(proposal,number,run,policy,envelope,api,verify=signer.verify)
        api=F.API(proposal,number,self.token if stage=='merge' else self.observer,self.observer)
        merged=api('GET','/pulls/'+str(number)).get('merged') is True
        if stage=='merge':
            C.require(callable(self.commit),'ACCEPTANCE_COMMIT_FENCE_REQUIRED')
            # A lost merge response must reconcile the accepted commit even
            # if somebody has already synchronized/closed its GitHub proposal.
            if not merged:observe()
            else:self.commit(job)
            def request(method,suffix,body=None):
                if method!='GET':
                    C.require(callable(self.staged),'ACCEPTANCE_STAGING_GATE_REQUIRED')
                    self.staged(job)
                    self.commit(job)
                return api(method,suffix,body)
            return F.merge(proposal,number,run,policy,envelope,receipts['review'],request,verify=signer.verify)
        C.require(merged,'ACCEPTANCE_SYNC_REQUIRES_MERGE')
        accepted=F.merge(proposal,number,run,policy,envelope,receipts['review'],api,verify=signer.verify)
        C.require(receipts['merge']['head']==accepted['head'] and receipts['merge']['proposal_sha256']==digest,
            'ACCEPTANCE_MERGE_RECEIPT_CHANGED')
        return H.sync(proposal,accepted,self.github)
