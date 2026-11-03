"""Invented repositories only. Real Git and both client/server hook execution."""
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.append(str(HERE.parents[1]/"forgejo"))
sys.path.append(str(HERE.parents[1]/"deployment/forgejo-governance-v2"))
import core as m
import lease
import entry
spec=importlib.util.spec_from_file_location('push_guard',HERE/'pre-push.py')
hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)
GIT='/nix/store/gy266y3ax8xvblz36m6an7h8mi485mf1-git-2.54.0/bin/git'


def bind(value):
    raw=json.dumps(value,sort_keys=True).encode()
    return m.Binding(raw,hashlib.sha256(raw).hexdigest())


def document():
    return dict(schema_version=1,base='1'*40,head='2'*40,tree='3'*40,
        workflow_sha256='a'*64,bundle_sha256='b'*64,bundle_bytes=42,evidence_sha256='c'*64)


class Contract(unittest.TestCase):
    def test_entry_gate_requires_deployed_unicast_and_durable_open_result(self):
        phase={'schema_version':1,'phase':'public-writes-open','elapsed_seconds':1}
        result={'schema_version':1,'code':'CUTOVER_VERIFIED','phase':'public-writes-open'}
        def reader(path,**_):return json.dumps(phase if path.name=='phase.json' else result).encode()
        bootstrap=SimpleNamespace(private_file=reader,parse=json.loads)
        with patch.object(entry.os.path,'realpath',return_value=entry.CURRENT):
            entry.gate(bootstrap)
            phase['schema_version']=True
            with self.assertRaisesRegex(m.Refused,'DEPLOYED_BASELINE_REFUSED'):entry.gate(bootstrap)
            phase['schema_version']=1;result['code']='INVENTED_FAILURE'
            with self.assertRaisesRegex(m.Refused,'DEPLOYED_BASELINE_REFUSED'):entry.gate(bootstrap)
        with patch.object(entry.os.path,'realpath',return_value='/nix/store/other'):
            with self.assertRaisesRegex(m.Refused,'DEPLOYED_BASELINE_REFUSED'):entry.gate(bootstrap)

    def test_binding_shape_and_safe_failure_projection(self):
        b=bind(document());self.assertNotIn('approved',b.body)
        for change in (lambda x:x.update(schema_version=True),lambda x:x.update(extra=True),
                       lambda x:x.update(base=x['head']),lambda x:x.update(bundle_bytes=2**20+1)):
            v=document();change(v)
            with self.assertRaises(m.Refused):bind(v)
        self.assertEqual(entry.failure(m.Refused('MAIN_CHANGED')),'MAIN_CHANGED')
        for e in (m.Refused('INVENTED_SECRET'),RuntimeError('MAIN_CHANGED'),ValueError('private token')):
            self.assertEqual(entry.failure(e),'RULES_PROPOSAL_REFUSED')

    def test_transport_has_no_review_status_merge_or_protection_mutation(self):
        b=bind(document());api=m.Transport('a'*40,b)
        self.assertTrue(api.endpoint_allowed('POST',m.BASE+'/pulls'))
        for method,path in [('POST',m.BASE+'/pulls/1/reviews'),('POST',m.BASE+'/statuses/'+b.value['head']),
                            ('POST',m.BASE+'/pulls/1/merge'),('PATCH',m.BASE+'/branch_protections/main'),
                            ('POST','/api/v1/orgs/MrJ-am/repos'),('GET','/api/v1/repos/MrJ-am/vision')]:
            self.assertFalse(api.endpoint_allowed(method,path))

    def test_hook_refuses_existing_oid_other_ref_remote_and_multiple_updates(self):
        b=bind(document());raw=(b.value['head']+' '+b.value['head']+' '+b.ref+' '+'0'*40+'\n').encode()
        self.assertTrue(hook.validate([m.URL,m.URL],raw,b.value))
        for altered in (raw.replace(b'0'*40,b'1'*40),raw.replace(b.ref.encode(),b'refs/heads/main'),
                        raw+raw,raw.replace(b'2'*40,b'3'*40),b''):
            self.assertFalse(hook.validate([m.URL,m.URL],altered,b.value))
        self.assertFalse(hook.validate([m.URL,'http://example.invalid'],raw,b.value))

    def test_existing_pr_requires_same_author_body_refs_commits_and_open_state(self):
        b=bind(document());observed={'author_id':1,'repository_id':2}
        row={'number':7,'state':'open','merged':False,'title':m.TITLE,'body':b.body,'user':{'id':1},
            'base':{'ref':'main','sha':b.value['base'],'repo':{'id':2}},
            'head':{'ref':b.branch,'sha':b.value['head'],'repo':{'id':2}}}
        self.assertEqual(m.validate_pr(row,b,observed),7)
        for change in (lambda x:x.update(state='closed'),lambda x:x.update(merged=True),
                       lambda x:x.update(body='different'),lambda x:x['user'].update(id=3),
                       lambda x:x['head'].update(sha='4'*40),lambda x:x['base']['repo'].update(id=8)):
            other=copy.deepcopy(row);change(other)
            with self.assertRaises(m.Refused):m.validate_pr(other,b,observed)


class NativeGit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.remote=self.root/'remote.git'
        self.env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',
            GIT_AUTHOR_NAME='Invented',GIT_AUTHOR_EMAIL='invented@example.invalid',
            GIT_COMMITTER_NAME='Invented',GIT_COMMITTER_EMAIL='invented@example.invalid',
            GIT_AUTHOR_DATE='2000-01-01T00:00:00Z',GIT_COMMITTER_DATE='2000-01-01T00:00:00Z')
        self.git('init','--initial-branch=main',str(self.source))
        (self.source/'README').write_text('invented source\n');self.git('-C',str(self.source),'add','README')
        self.git('-C',str(self.source),'commit','-m','invented base')
        base=self.git('-C',str(self.source),'rev-parse','HEAD').strip().decode()
        self.git('clone','--bare',str(self.source),str(self.remote))
        workflow=(HERE.parents[1]/'forgejo/independent-validation.yml').read_bytes()
        target=self.source/m.WORKFLOW;target.parent.mkdir(parents=True);target.write_bytes(workflow)
        self.git('-C',str(self.source),'add',m.WORKFLOW);self.git('-C',str(self.source),'commit','-m','invented proposal')
        head=self.git('-C',str(self.source),'rev-parse','HEAD').strip().decode()
        tree=self.git('-C',str(self.source),'rev-parse','HEAD^{tree}').strip().decode()
        ref='refs/heads/bootstrap-ci-workflow-'+head[:16]
        self.git('-C',str(self.source),'update-ref',ref,head)
        bundle=self.root/'proposal.bundle';self.git('-C',str(self.source),'bundle','create','--version=2',str(bundle),ref,'^'+base)
        self.raw=bundle.read_bytes()
        self.b=bind(dict(schema_version=1,base=base,head=head,tree=tree,workflow_sha256=hashlib.sha256(workflow).hexdigest(),
            bundle_sha256=hashlib.sha256(self.raw).hexdigest(),bundle_bytes=len(self.raw),evidence_sha256='a'*64))
        bp=self.root/'binding.json';bp.write_text(json.dumps(self.b.value,sort_keys=True))
        self.hooks=self.root/'hooks';self.hooks.mkdir()
        code=(HERE/'pre-push.py').read_text().replace('@BINDING@',str(bp)).replace('@BINDING_SHA256@',hashlib.sha256(bp.read_bytes()).hexdigest())
        code=code.replace(m.URL,self.remote.as_uri()) # fixture local transport only
        hp=self.hooks/'pre-push';hp.write_text('#!'+sys.executable+'\n'+code);hp.chmod(0o755)
        self.marker=self.root/'server-hook-ran'
        sp=self.remote/'hooks/pre-receive';sp.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\nPath('+repr(str(self.marker))+').write_bytes(sys.stdin.buffer.read())\n');sp.chmod(0o755)
        p=patch.object(m,'URL',self.remote.as_uri());p.start();self.addCleanup(p.stop)
        p=patch.object(m,'STATE',self.root);p.start();self.addCleanup(p.stop)
        self.client=m.Git(GIT,'',str(self.hooks),self.b)

    def git(self,*args):
        p=subprocess.run([GIT,*args],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=30)
        self.assertEqual(p.returncode,0,'invented Git operation failed')
        return p.stdout

    def test_create_and_identical_replay_keep_main_and_server_hook(self):
        self.assertTrue(self.client.prepare_and_push(self.raw))
        self.assertTrue(self.marker.is_file())
        self.assertFalse(self.client.prepare_and_push(self.raw))
        self.assertEqual(self.client.refs(),{'refs/heads/main':self.b.value['base'],self.b.ref:self.b.value['head']})

    def test_preexisting_different_branch_refuses_without_mutation(self):
        self.git('--git-dir='+str(self.remote),'update-ref',self.b.ref,self.b.value['base'])
        with self.assertRaisesRegex(m.Refused,'PROPOSAL_BRANCH_CONFLICT'):self.client.prepare_and_push(self.raw)
        self.assertFalse(self.marker.exists())

    def test_concurrent_branch_at_push_refuses_real_fast_forward(self):
        def raced(args,**kw):
            if 'push' in args:self.git('--git-dir='+str(self.remote),'update-ref',self.b.ref,self.b.value['base'])
            return subprocess.run(args,**kw)
        self.client.run=raced
        with self.assertRaisesRegex(m.Refused,'GIT_OPERATION_REFUSED'):self.client.prepare_and_push(self.raw)
        self.assertEqual(self.git('--git-dir='+str(self.remote),'rev-parse',self.b.ref).strip().decode(),self.b.value['base'])
        self.assertFalse(self.marker.exists())

    def test_changed_workflow_digest_refuses_before_push(self):
        self.client.binding=bind(self.b.value|{'workflow_sha256':'0'*64})
        with self.assertRaisesRegex(m.Refused,'WORKFLOW_BYTES_REFUSED'):self.client.prepare_and_push(self.raw)
        self.assertFalse(self.marker.exists())


class LeaseOrder(unittest.TestCase):
    def exercise(self, *, restriction_fails=False, body_fails=False):
        events=[];state={'restricted':False,'revoked':False,'count':0}
        @contextmanager
        def lock():yield
        class API:
            def __init__(self,token):pass
            def get(self,path):
                events.append('api')
                if state['revoked']:return 401,None
                self_check=state['restricted'];self_outer.assertTrue(self_check,'network before restriction')
                return 200,{'version':'17.0.1'}
        self_outer=self
        b=SimpleNamespace(locked=lock,validate_configuration=lambda:None,validate_running=lambda:None,
            cleanup=lambda:None,identity_attested=lambda:True,sql=lambda *_:{'eligible':True},
            FORGEJO='/fixed/forgejo',INI=Path('/fixed/ini'),API=API)
        def command(args):
            self.assertIn(lease.SCOPES,args);events.append('issue');state['count']=1;return b'a'*40+b'\n'
        b.command=command
        def sql(_,op,label):
            if op=='count':return state['count']
            events.append(op)
            if restriction_fails:raise lease.Refused('LEASE_SQL_RESULT_REFUSED')
            state['restricted']=True
        def cleanup(_):events.append('revoke');state.update(revoked=True,count=0)
        # Initial cleanup is inert; final cleanup represents the exact revoke path.
        def cleanup_first_then_revoke(_):
            if state['count']:cleanup(_)
        with patch.object(lease,'sql',side_effect=sql),patch.object(lease,'publish',side_effect=lambda *_:None), \
             patch.object(lease,'cleanup',side_effect=cleanup_first_then_revoke):
            if restriction_fails or body_fails:
                with self.assertRaises(lease.Refused):
                    with lease.repository_lease(b):
                        if body_fails:raise lease.Refused('INVENTED_FAILURE')
            else:
                with lease.repository_lease(b):events.append('body')
        self.assertTrue(state['revoked']);self.assertEqual(state['count'],0)
        self.assertEqual(events[:2],['issue','restrict'])
        if restriction_fails:self.assertNotIn('body',events)
        return events

    def test_restriction_precedes_first_network_and_revocation_follows(self):self.exercise()
    def test_restriction_failure_revokes_before_any_authenticated_use(self):self.exercise(restriction_fails=True)
    def test_body_failure_still_revokes(self):self.exercise(body_fails=True)


if __name__=='__main__':unittest.main()
