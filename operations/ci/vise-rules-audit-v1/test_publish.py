import copy
import hashlib
import json
from contextlib import contextmanager, nullcontext
from pathlib import Path
import unittest
from unittest.mock import patch
import publish as P

ROOT=Path(__file__).resolve().parents[1]
REPORT=Path('/nix/store/74329d2w5p244s4rvpfip1c70cvb4qid-mrjam-vise-rules-independent-audit-1/report.json').read_bytes()

class Publisher(unittest.TestCase):
    def setUp(self):
        raw=(ROOT/'vise-rules-proposal-v1/binding.json').read_bytes()
        self.binding=P.core.Binding(raw,hashlib.sha256(raw).hexdigest())
        self.rows=[];self.calls=[];self.closed=False
        self.protected=True;self.main=self.binding.value['base']
        self.pr={'number':2,'state':'open','merged':False,'title':P.core.TITLE,
            'body':self.binding.body,'user':{'id':42}}
        for k,ref in [('base','main'),('head',self.binding.branch)]:
            self.pr[k]={'ref':ref,'sha':self.binding.value[k],'repo':{'id':7}}
        self.commit={'sha':P.HEAD,'commit':{'tree':{'sha':self.binding.value['tree']}},
            'parents':[{'sha':self.binding.value['base']}]}
        @contextmanager
        def lease(_):
            self.calls.append('lease')
            try: yield 'a'*40
            finally:self.closed=True
        self.enterContext(patch.object(P.lease,'repository_lease',lease))
        self.enterContext(patch.object(P.core.credentials,'broker',lambda *_:nullcontext()))
        self.git_check=self.enterContext(patch.object(P,'verify_git'))
        def protect(_):
            P.core.require(self.protected,'MAIN_PROTECTION_REFUSED');return True
        self.enterContext(patch.object(P.protection,'verify',protect))

    def request(self,method,path,body=None):
        self.calls.append((method,path))
        if method=='POST':
            self.assertEqual((path,body),(P.POST,P.BODY))
            row={**body,'id':8,'creator':{'id':42}};row['status']=row.pop('state')
            self.rows=[row];return self.rows[0]
        if path=='/api/v1/version':return {'version':'17.0.1'}
        if path=='/api/v1/settings/api':return {'max_response_items':50}
        if path=='/api/v1/user':return {'id':42,'login':P.lease.ACCOUNT,'is_admin':True}
        if path==P.BASE:return {'id':7,'full_name':'MrJ-am/mrjam-validation','private':True,
            'empty':False,'archived':False,'mirror':False,'default_branch':'main','has_actions':True}
        if path==P.BASE+'/branches/main':return {'name':'main','commit':{'id':self.main}}
        if path==P.PULL:return self.pr
        if path==P.COMMIT:return self.commit
        if path==P.STATUSES:return copy.deepcopy(self.rows)
        self.fail('Unexpected endpoint')

    def run_publish(self,raw=REPORT):
        return P.publish(raw,self.binding,object(),object(),transport=lambda *_:self)

    def assert_no_write(self):
        self.assertFalse(any(isinstance(c,tuple) and c[0]!='GET' for c in self.calls))

    def test_publish_then_retry_only_reads(self):
        first=self.run_publish();second=self.run_publish()
        self.assertTrue(first['created']);self.assertFalse(second['created'])
        self.assertEqual(self.calls.count(('POST',P.POST)),1)
        self.assertTrue(self.closed);self.assertFalse(first['review_created'])

    def test_report_substitution_refused_before_lease(self):
        value=json.loads(REPORT);value['head']='f'*40
        with self.assertRaises(P.core.Refused):self.run_publish(json.dumps(value).encode())
        self.assertEqual(self.calls,[])

    def test_each_live_binding_change_refuses_without_write(self):
        cases=[('head',self.pr['head'],'sha'),('base',self.pr['base'],'sha'),
            ('parent',self.commit['parents'][0],'sha')]
        for name,obj,key in cases:
            with self.subTest(name=name):
                old=obj[key];obj[key]='f'*40;self.calls=[]
                with self.assertRaises(P.core.Refused):self.run_publish()
                self.assert_no_write();self.assertTrue(self.closed);obj[key]=old

    def test_native_git_rejection_prevents_status_write(self):
        self.git_check.side_effect=P.core.Refused('PROPOSAL_TREE_REFUSED')
        with self.assertRaisesRegex(P.core.Refused,'PROPOSAL_TREE_REFUSED'):self.run_publish()
        self.assert_no_write();self.assertTrue(self.closed)

    def test_main_moved_or_protection_changed_refuses(self):
        self.main='f'*40
        with self.assertRaises(P.core.Refused):self.run_publish()
        self.assert_no_write();self.main=self.binding.value['base'];self.protected=False
        with self.assertRaises(P.core.Refused):self.run_publish()
        self.assert_no_write()

    def test_other_or_failed_context_cannot_be_overwritten(self):
        for change in ({'status':'failure'},{'creator':{'id':99}},{'description':'invented'}):
            row={**P.BODY,'id':8,'creator':{'id':42}};row['status']=row.pop('state')
            self.rows=[{**row,**change}]
            with self.assertRaises(P.core.Refused):self.run_publish()
            self.assert_no_write()

    def test_missing_readback_fails_and_releases_lease(self):
        original=self.request
        def request(method,path,body=None):
            result=original(method,path,body)
            if method=='POST':self.rows=[]
            return result
        self.request=request
        with self.assertRaisesRegex(P.core.Refused,'AUDIT_READBACK_REFUSED'):self.run_publish()
        self.assertTrue(self.closed)

    def test_full_status_page_refuses_incomplete_observation(self):
        self.rows=[{'context':'other'} for _ in range(50)]
        with self.assertRaisesRegex(P.core.Refused,'AUDIT_STATUS_PAGE_REFUSED'):self.run_publish()
        self.assert_no_write()

    def test_transport_denies_other_mutations_and_payloads(self):
        api=P.Transport('a'*40,self.binding)
        for method,path in [('POST',P.PULL+'/merge'),('POST',P.PULL+'/reviews'),
            ('POST',P.BASE+'/pulls'),('PATCH',P.BASE+'/branch_protections/main'),
            ('POST',P.BASE+'/statuses/'+'f'*40)]:
            self.assertFalse(api.endpoint_allowed(method,path))
        with self.assertRaisesRegex(P.core.Refused,'AUDIT_BODY_REFUSED'):
            api.request('POST',P.POST,{**P.BODY,'state':'failure'})

if __name__=='__main__':unittest.main()
