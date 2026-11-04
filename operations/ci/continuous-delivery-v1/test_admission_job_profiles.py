import json,tempfile,unittest
from pathlib import Path
import test_admission_orchestrator as T
import admission_profiles as P

def ready(repository,number):
    item=T.ready(number);proposal=T.T.proposal(number=number,repository=repository)
    item['job'].update(proposal=json.dumps(proposal),key=T.T.Q.key(proposal))
    return item

class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.platform=T.Adapter();self.vise=T.Adapter()
        self.item=ready('etp-vie-affective',1);self.other=ready('mrjam-plateforme',2)
        self.dispatch=P.Profiles(self.platform,vise=self.vise)

    def test_repository_identity_selects_installed_adapter(self):
        self.dispatch.check_ready(self.item)
        self.dispatch.capture(self.root,{'ready':self.item})
        self.assertEqual(self.vise.calls,['capture']);self.assertEqual(self.platform.calls,[])
        self.dispatch.construct(self.root,{'ready':self.other})
        self.assertEqual(self.platform.calls,['construct'])

    def test_missing_vise_is_job_refusal_and_platform_advances(self):
        dispatcher=P.Profiles(self.platform)
        first=T.O.tick(self.root,[self.item],dispatcher,clock=lambda:10)
        self.assertEqual(first['code'],'PROJECT_RECIPE_UNAVAILABLE')
        second=T.O.tick(self.root,[self.item,self.other],dispatcher,clock=lambda:11)
        self.assertEqual(second['job'],T.O.identity(self.other));self.assertEqual(second['phase'],'captured')

    def test_validated_profile_failure_does_not_escape_retry_boundary(self):
        for now in range(10,30):
            result=T.O.tick(self.root,[self.item],self.dispatch,clock=lambda:now)
            if result.get('phase')=='validated':break
        else:self.fail('validated phase not reached')
        def failed(value):raise T.O.W.Q.S.Refused('VISE_ADOPTION_UNAVAILABLE')
        self.vise.current=failed
        result=T.O.tick(self.root,[self.item],self.dispatch,clock=lambda:30)
        self.assertEqual(result['code'],'VISE_ADOPTION_UNAVAILABLE')
        result=T.O.tick(self.root,[self.item,self.other],self.dispatch,clock=lambda:31)
        self.assertEqual(result['job'],T.O.identity(self.other));self.assertEqual(result['phase'],'captured')

    def test_wrong_repository_id_is_not_a_profile_override(self):
        proposal=json.loads(self.item['job']['proposal']);proposal['repository_id']=1
        self.item['job']['proposal']=json.dumps(proposal)
        with self.assertRaisesRegex(P.W.Q.P.A.Refused,'PULL_BASE_REFUSED'):
            self.dispatch.selected({'ready':self.item})
        self.assertEqual(self.platform.calls,[]);self.assertEqual(self.vise.calls,[])

    def test_staging_keeps_both_adopted_profiles_and_current_candidate(self):
        self.platform.adopted=lambda:({'proposal_sha256':'a'*64,'source':'platform-source'},{'rules_revision':'1'*40},None)
        self.vise.adopted=lambda:({'proposal_sha256':'b'*64,'source':'vise-source'},{'rules_revision':'2'*40},None)
        result=self.dispatch.staging({'ready':self.item},{'proposal_sha256':'c'*64,'source':'candidate-source'})
        self.assertEqual(result['schema_version'],2)
        self.assertEqual([e['rules_revision'] for e in result['proposals']],['1'*40,'2'*40,'2'*40])
        self.assertEqual(len(result['proposals']),3)

    def test_unavailable_other_adoption_does_not_block_current_profile(self):
        self.platform.adopted=lambda:({'proposal_sha256':'a'*64,'source':'platform-source'},{'rules_revision':'1'*40},None)
        def missing():raise FileNotFoundError('synthetic missing ViSe descriptor')
        self.vise.adopted=missing
        data={'proposal_sha256':'c'*64,'source':'candidate-source'}
        self.assertEqual(len(self.dispatch.staging({'ready':self.other},data)['proposals']),2)
        with self.assertRaises(FileNotFoundError):self.dispatch.staging({'ready':self.item},data)

if __name__=='__main__':unittest.main()
