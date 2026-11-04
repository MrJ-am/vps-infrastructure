import json,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import test_promotion_service
import acceptance_adapter as A

class Adapter(unittest.TestCase):
    def setUp(self):
        self.proposal={'repository':'mrjam-plateforme','repository_id':1437120781,'number':7,
            'draft':False,'branch':'synthetic','head':'b'*40,'base':'a'*40}
        self.job={'capture':{'proposal':self.proposal,'proposal_sha256':'c'*64},'ready':{'base_sha256':'d'*64},'run':{'id':9}}
        self.expected={'repository':'MrJ-am/mrjam-plateforme','revision':'b'*40,'tree_sha':'e'*40}
        self.receipts={'mirror':{'number':3,'repository':'mrjam-plateforme','head':'b'*40,'proposal_sha256':'c'*64},
            'review':{'review_id':8},'merge':{'head':'b'*40,'proposal_sha256':'c'*64}}
    def adapter(self,stage):return A.Adapter(stage,{},'synthetic-observer',None if stage=='sync' else 'synthetic-'+stage,'/synthetic/git',commit=Mock(),staged=Mock())
    def verified(self):return self.proposal,{}, {},{'id':9},self.expected
    def test_cross_role_execution_refused_before_authority_read(self):
        a=self.adapter('mirror')
        with patch.object(a,'verified') as verified:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_SERVICE_STAGE_REFUSED'):a.execute('merge',Path('/synthetic'),self.job,{})
            verified.assert_not_called()
    def test_sync_rejects_forgejo_write_credential(self):
        with self.assertRaisesRegex(Exception,'ACCEPTANCE_CREDENTIAL_ROLE_REFUSED'):A.Adapter('sync',{},'reader','writer')
    def test_vise_disabled_refuses_before_adoption_or_remote_access(self):
        self.proposal.update(repository='etp-vie-affective',repository_id=1433178398)
        with patch.object(A.Path,'read_bytes') as read,patch.object(A.A,'load') as load:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_PROFILE_NOT_INSTALLED'):
                self.adapter('review').verified(Path('/synthetic'),self.job)
            read.assert_not_called();load.assert_not_called()
    def test_each_profile_checks_its_own_adopted_base_before_signature(self):
        for repository,identity,path in [('mrjam-plateforme',1437120781,'/etc/mrjam-delivery-adopted.json'),
                ('etp-vie-affective',1433178398,'/etc/mrjam-vise-delivery-adopted.json')]:
            self.proposal.update(repository=repository,repository_id=identity)
            adapter=A.Adapter('review',{},'observer','reviewer',enable_vise=True)
            with patch.object(A.Path,'read_bytes',autospec=True,return_value=b'{"proposal_sha256":"stale"}') as read,\
                    patch.object(A.A,'load') as load:
                with self.assertRaisesRegex(Exception,'ACCEPTANCE_ADOPTED_BASE_CHANGED'):
                    adapter.verified(Path('/synthetic'),self.job)
                read.assert_called_once_with(Path(path));load.assert_not_called()
    def test_repository_identity_mismatch_never_selects_adoption(self):
        self.proposal.update(repository='etp-vie-affective')
        with patch.object(A.Path,'read_bytes') as read:
            with self.assertRaises(Exception):self.adapter('review').verified(Path('/synthetic'),self.job)
            read.assert_not_called()
    def test_invalid_signature_prevents_any_remote_call(self):
        a=self.adapter('review')
        with patch.object(A.Path,'read_bytes',return_value=json.dumps({'proposal_sha256':'d'*64}).encode()),\
                patch.object(A.A,'load',return_value={'authority':{}}),\
                patch.object(A.C,'regular_file',return_value=b'{"payload":{"proposal_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}}'),\
                patch.object(A.signer,'verify',return_value=False),patch.object(A.http.client,'HTTPConnection') as connection:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_SIGNATURE_REFUSED'):a.verified(Path('/synthetic'),self.job)
            connection.assert_not_called()
    def test_review_observes_source_before_approval(self):
        a=self.adapter('review')
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.S,'observe',return_value={}),patch.object(A.V,'approve') as approve:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_REMOTE_SOURCE_CHANGED'):a.execute('review',Path('/synthetic'),self.job,self.receipts)
            approve.assert_not_called()
    def test_lost_merge_response_reconciles_even_if_github_pr_is_closed(self):
        a=self.adapter('merge');api=Mock(return_value={'merged':True})
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),\
                patch.object(A.S,'observe',side_effect=AssertionError('closed GitHub PR must not be observed')),\
                patch.object(A.F,'merge',return_value={'reconciled':True}) as merge:
            self.assertEqual(a.execute('merge',Path('/synthetic'),self.job,self.receipts),{'reconciled':True});merge.assert_called_once()
    def test_sync_rechecks_canonical_merge_with_read_only_observer(self):
        a=self.adapter('sync');api=Mock(return_value={'merged':True})
        accepted={'head':'b'*40,'proposal_sha256':'c'*64}
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api) as factory,\
                patch.object(A.F,'merge',return_value=accepted),patch.object(A.H,'sync',return_value={'synced':True}):
            self.assertEqual(a.execute('sync',Path('/synthetic'),self.job,self.receipts),{'synced':True})
            self.assertEqual(factory.call_args.args[2:],('synthetic-observer','synthetic-observer'))
    def test_sync_cannot_create_a_missing_merge(self):
        a=self.adapter('sync');api=Mock(return_value={'merged':False})
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),patch.object(A.F,'merge') as merge:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_SYNC_REQUIRES_MERGE'):a.execute('sync',Path('/synthetic'),self.job,self.receipts)
            merge.assert_not_called()
    def test_merge_preflight_failure_never_acquires_fence(self):
        a=self.adapter('merge');api=Mock(return_value={'merged':False})
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),\
                patch.object(A.S,'observe',return_value=self.expected),\
                patch.object(A.F,'merge',side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):a.execute('merge',Path('/synthetic'),self.job,self.receipts)
            a.commit.assert_not_called()
    def test_fence_precedes_remote_write_and_failure_prevents_it(self):
        for refuse in (False,True):
            a=self.adapter('merge');events=[]
            def commit(job):
                events.append('durable-fence')
                if refuse:raise TimeoutError()
            a.commit=commit
            def api(method,suffix,body=None):
                if method=='POST':events.append('remote-write')
                return {'merged':False}
            def merge(*args,**kwargs):return args[6]('POST','/pulls/3/merge',{})
            with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),\
                    patch.object(A.S,'observe',return_value=self.expected),patch.object(A.F,'merge',side_effect=merge):
                if refuse:
                    with self.assertRaises(TimeoutError):a.execute('merge',Path('/synthetic'),self.job,self.receipts)
                    self.assertEqual(events,['durable-fence'])
                else:
                    a.execute('merge',Path('/synthetic'),self.job,self.receipts)
                    self.assertEqual(events,['durable-fence','remote-write'])
    def test_unready_stage_prevents_fence_and_remote_write(self):
        a=self.adapter('merge');a.staged.side_effect=RuntimeError('not staged')
        api=Mock(return_value={'merged':False})
        def merge(*args,**kwargs):return args[6]('POST','/pulls/3/merge',{})
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),\
                patch.object(A.S,'observe',return_value=self.expected),patch.object(A.F,'merge',side_effect=merge):
            with self.assertRaisesRegex(RuntimeError,'not staged'):a.execute('merge',Path('/synthetic'),self.job,self.receipts)
            a.commit.assert_not_called()
            self.assertTrue(all(call.args[0]=='GET' for call in api.call_args_list))
    def test_gate_is_checked_immediately_before_fence_and_merge(self):
        a=self.adapter('merge');events=[]
        a.staged=lambda job:events.append('staged');a.commit=lambda job:events.append('fenced')
        def api(method,suffix,body=None):
            if method=='POST':events.append('merged')
            return {'merged':False}
        def merge(*args,**kwargs):return args[6]('POST','/pulls/3/merge',{})
        with patch.object(a,'verified',return_value=self.verified()),patch.object(A.F,'API',return_value=api),\
                patch.object(A.S,'observe',return_value=self.expected),patch.object(A.F,'merge',side_effect=merge):
            a.execute('merge',Path('/synthetic'),self.job,self.receipts)
        self.assertEqual(events,['staged','fenced','merged'])

if __name__=='__main__':unittest.main()
