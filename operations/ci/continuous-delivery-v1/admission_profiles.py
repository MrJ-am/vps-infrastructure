"""Dispatch jobs to installed adapters using the exact repository identity.

Availability is checked while advancing an individual job, not while ingesting
the ready list. A missing ViSe implementation therefore cannot reject the whole
batch. No proposal field selects an executable, policy path, or trust anchor.
"""
import json
import delivery_profiles as D
import intake_prepare as W
from source_snapshot import require

class Profiles:
    def __init__(self,platform,*,vise=None):
        self.adapters={'platform':platform}
        if vise is not None:self.adapters['vise']=vise
        for adapter in self.adapters.values():adapter.staging_catalog=self.staging

    def profile(self,item):
        proposal=W.Q.checked(json.loads(item['job']['proposal']))
        return D.selected(proposal)

    def check_ready(self,item):
        self.adapters['platform'].check_ready(item)
        self.profile(item)

    def selected(self,value):
        name=self.profile(value['ready'])
        require(name in self.adapters,'PROJECT_RECIPE_UNAVAILABLE')
        return self.adapters[name]

    def staging(self,value,data):
        current=self.selected(value);entries={};rules=None
        for adapter in self.adapters.values():
            try:adopted,policy,_=adapter.adopted()
            except Exception as error:
                # Other profiles' disposable CI input copies are optional.
                # An unavailable ViSe descriptor must not block platform work.
                # No application data or persistent runtime is removed here.
                if adapter is current or not (isinstance(error,(OSError,ValueError)) or type(error).__name__=='Refused'):
                    raise
                continue
            revision=policy['rules_revision']
            if adapter is current:rules=revision
            entries[adopted['proposal_sha256']]={'sha256':adopted['proposal_sha256'],
                'source_store':adopted['source'],'rules_revision':revision}
        require(rules is not None,'ADOPTED_RULES_MISSING')
        entries[data['proposal_sha256']]={'sha256':data['proposal_sha256'],
            'source_store':data['source'],'rules_revision':rules}
        return {'schema_version':2,'proposals':[entries[key] for key in sorted(entries)]}

    def current(self,value):return self.selected(value).current(value)
    def observe(self,value):return self.selected(value).observe(value)
    def run_boundary(self,value):return self.selected(value).run_boundary(value)
    def dispatch(self,value):return self.selected(value).dispatch(value)
    def poll(self,value):return self.selected(value).poll(value)
    def capture(self,path,value):return self.selected(value).capture(path,value)
    def construct(self,path,value):return self.selected(value).construct(path,value)
    def admit(self,path,value):return self.selected(value).admit(path,value)
    def capture_artifacts(self,path,value):return self.selected(value).capture_artifacts(path,value)
    def feedback(self,path,value):return self.selected(value).feedback(path,value)
    def decision(self,value,action):return self.selected(value).decision(value,action)
