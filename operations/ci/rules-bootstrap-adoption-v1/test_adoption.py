"""Synthetic decisions and real local checkpoints; no production request."""
from contextlib import contextmanager
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
for directory in (HERE.parent/'authority-v1',HERE.parent/'review-v1',
                  Path('/nix/store/1j61zvqin8df0vdazsdxlfssf5rdc54z-mrjam-rules-bootstrap-proposal-1/libexec'),HERE):
    sys.path.insert(0,str(directory))
spec=importlib.util.spec_from_file_location('sso',HERE.parents[1]/'deployment/forgejo_sso_probe.py')
sso=importlib.util.module_from_spec(spec);sys.modules['sso']=sso;spec.loader.exec_module(sso)
import adoption as m
import identity


def row(**changes):
    return dict(id=7,reviewer_id=1,state='APPROVED',body=m.TEXT,commit_id='2'*40,
        official=True,stale=False,dismissed=False,updated_at=100)|changes


class Review(unittest.TestCase):
    def test_native_participants_include_approval_and_exclude_dismissed_comments(self):
        rows=[row(),row(id=8,reviewer_id=3,state='COMMENT'),
              row(id=9,reviewer_id=4,state='REQUEST_CHANGES',dismissed=True)]
        m.verify_review_participants([1],rows)
        for requested in ([],[1,3],[1,5]):
            with self.assertRaisesRegex(m.Refused,'REVIEW_PARTICIPANTS_CHANGED'):
                m.verify_review_participants(requested,rows)
        rows.append(row(id=10,reviewer_id=3,state='REQUEST_REVIEW'))
        m.verify_review_participants([1,3],rows)
        with self.assertRaisesRegex(m.Refused,'REVIEW_REQUEST_UNRESOLVED'):
            m.select_review(rows,1,2,'2'*40,101)

    def test_exact_review_with_external_whitespace_and_crlf(self):
        for body in (m.TEXT,' \r\n'+m.TEXT+'\r\n '):
            self.assertEqual(m.select_review([row(body=body)],1,2,'2'*40,101)['body'],m.TEXT)

    def test_identity_head_state_and_body_refusals(self):
        for change in ({'reviewer_id':2},{'commit_id':'3'*40},{'official':False},{'stale':True},
                       {'dismissed':True},{'state':'COMMENT'},{'state':'OTHER'},
                       {'body':m.TEXT+' extra'},{'body':'prefix '+m.TEXT},{'updated_at':102},{'official':1}):
            with self.subTest(change=change):
                with self.assertRaises(m.Refused):m.select_review([row(**change)],1,2,'2'*40,101)
        with self.assertRaises(m.Refused):m.select_review([],1,2,'2'*40,101)
        with self.assertRaises(m.Refused):m.select_review([row()],1,1,'2'*40,101)

    def test_later_revocation_or_other_reviewer_request_blocks(self):
        for r in (row(id=8,state='REQUEST_CHANGES',updated_at=101),
                  row(id=8,reviewer_id=3,state='REQUEST_REVIEW')):
            with self.assertRaises(m.Refused):m.select_review([row(),r],1,2,'2'*40,101)
        self.assertEqual(m.select_review([row(),row(id=8,reviewer_id=3,state='REQUEST_CHANGES',dismissed=True)],1,2,'2'*40,101)['id'],7)

    def test_editing_older_approval_cannot_hide_newer_native_rejection(self):
        with self.assertRaisesRegex(m.Refused,'REVIEW_REQUEST_UNRESOLVED'):
            m.select_review([row(id=1,updated_at=102),row(id=2,state='REQUEST_CHANGES',updated_at=101)],1,2,'2'*40,103)
        self.assertEqual(m.select_review([row(id=1,updated_at=102),
            row(id=2,state='REQUEST_CHANGES',updated_at=101,dismissed=True)],1,2,'2'*40,103)['id'],1)

    def test_review_pagination_complete_and_count_drift_duplicate_partial_refused(self):
        first=[row(id=i+1) for i in range(50)]
        pages=iter([(first,{'x-total-count':'51'}),([row(id=51)],{'x-total-count':'51'})])
        with patch.object(m.A,'review_projection',side_effect=lambda value:value):
            self.assertEqual(len(m.reviews(SimpleNamespace(get=lambda path:next(pages)))),51)
            for values in (
                [(first,{'x-total-count':'51'}),([row(id=51)],{'x-total-count':'52'})],
                [(first,{'x-total-count':'51'}),([row(id=1)],{'x-total-count':'51'})],
                [([row()],{'x-total-count':'2'})],
                [([row()],{'x-total-count':'0'})],
                [([row()],{'x-total-count':'10001'})]):
                pages=iter(values)
                with self.assertRaises(m.Refused):m.reviews(SimpleNamespace(get=lambda path:next(pages)))

    def test_native_identity_checks_and_id_share_readonly_snapshot(self):
        seen=[]
        bootstrap=SimpleNamespace(PSQL='/fixed/psql',command=lambda args,raw:seen.append((args,raw)) or
            (json.dumps(dict.fromkeys(sso.CHECKS,True))+'\n42\n').encode())
        with patch.object(sso,'subject_from_binding',return_value='00000000-0000-4000-8000-000000000001'):
            self.assertEqual(identity.owner(bootstrap),42)
        self.assertIn(b'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;',seen[0][1])
        self.assertNotIn('00000000-0000-4000-8000-000000000001',' '.join(seen[0][0]))
        for result in ((json.dumps(dict.fromkeys(sso.CHECKS,False))+'\n42\n').encode(),
                       (json.dumps(dict.fromkeys(sso.CHECKS,True))+'\n42\n43\n').encode()):
            bootstrap.command=lambda *args:result
            with patch.object(sso,'subject_from_binding',return_value='00000000-0000-4000-8000-000000000001'):
                with self.assertRaises(identity.Refused):identity.owner(bootstrap)


@contextmanager
def token(*_):yield 'a'*40


class Engine(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.binding=SimpleNamespace(value={'base':'1'*40,'head':'2'*40,'tree':'3'*40})
        self.bootstrap=SimpleNamespace(private_file=lambda p,**kw:p.read_bytes(),parse=json.loads)
        self.observed={'repository_id':3,'author_id':2,'owner_id':1,'review':row()}
        self.refs={'refs/heads/main':'1'*40,'refs/heads/proposal':'2'*40}
        self.merges=[]
        replacements=((m.proposal,'STATE',self.path),(m.proposal,'private_bundle',lambda *args:b'invented'),
            (m.lease,'repository_lease',token),(m.credentials,'broker',token),
            (m,'verify_source',lambda *args:None),(m,'observe',lambda *args,**kw:copy.deepcopy(self.observed)),
            (m,'references',lambda *args,merged=False:self.refs|({'refs/heads/main':'2'*40} if merged else {})))
        for obj,key,value in replacements:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)

    def invoke(self,merge=None):
        return m.adopt(self.binding,object(),self.bootstrap,reader_factory=lambda *args:object(),
            merge=merge or (lambda *args:self.merges.append(args)))

    def journal(self):return json.loads((self.path/m.Journal.NAME).read_text())

    def test_positive_and_replay_create_one_exact_native_request_only(self):
        result=self.invoke();self.assertEqual(result['code'],'RULES_BOOTSTRAP_MERGED_REVIEW_RECHECKED')
        self.assertEqual(self.merges,[('a'*40,'2'*40)])
        self.assertFalse(result['ci_attestation_issued']);self.assertFalse(result['activation_performed'])
        self.assertEqual(self.invoke(),result);self.assertEqual(len(self.merges),1)

    def test_missing_review_refuses_before_journal_or_merge(self):
        with patch.object(m,'observe',side_effect=m.Refused('HUMAN_REVIEW_REQUIRED')):
            with self.assertRaisesRegex(m.Refused,'HUMAN_REVIEW_REQUIRED'):self.invoke()
        self.assertEqual(self.merges,[]);self.assertFalse((self.path/m.Journal.NAME).exists())

    def test_review_changes_immediately_before_merge_refuse(self):
        changed=self.observed|{'review':row(id=8)}
        with patch.object(m,'observe',side_effect=[self.observed,changed]):
            with self.assertRaisesRegex(m.Refused,'PREMERGE_OBSERVATION_CHANGED'):self.invoke()
        self.assertEqual(self.merges,[])

    def test_revocation_after_merge_holds_without_undo_or_authority(self):
        with patch.object(m,'observe',side_effect=[self.observed,self.observed,m.Refused('HUMAN_REVIEW_REQUIRED')]):
            with self.assertRaisesRegex(m.Refused,'RULES_BOOTSTRAP_HELD'):self.invoke()
        self.assertEqual(len(self.merges),1);self.assertEqual(self.journal()['phase'],'merge-held')
        with self.assertRaisesRegex(m.Refused,'RULES_BOOTSTRAP_HELD'):self.invoke()
        self.assertEqual(len(self.merges),1)

    def test_http_ambiguity_is_resolved_only_by_full_positive_readback(self):
        def lost(*args):self.merges.append(args);raise m.merge_transport.Refused('MERGE_HTTP_REFUSED')
        self.assertEqual(self.invoke(lost)['code'],'RULES_BOOTSTRAP_MERGED_REVIEW_RECHECKED')
        self.assertEqual(self.journal()['phase'],'merged-reviewed')

    def test_unknown_merge_outcome_is_held_without_claiming_merge(self):
        def lost(*args):self.merges.append(args);raise m.merge_transport.Refused('MERGE_HTTP_REFUSED')
        with patch.object(m,'observe',side_effect=[self.observed,self.observed,m.Refused('MERGE_RESULT_REFUSED')]):
            with self.assertRaisesRegex(m.Refused,'RULES_BOOTSTRAP_HELD'):self.invoke(lost)
        self.assertEqual(self.journal()['phase'],'merge-held')

    def test_another_head_tag_change_after_merge_holds(self):
        def refs(*args,merged=False):
            return self.refs|({'refs/heads/main':'2'*40,'refs/tags/unexpected':'3'*40} if merged else {})
        with patch.object(m,'references',refs):
            with self.assertRaisesRegex(m.Refused,'RULES_BOOTSTRAP_HELD'):self.invoke()
        self.assertEqual(self.journal()['phase'],'merge-held')

    def test_interrupted_request_recovery_observes_only_never_posts_twice(self):
        journal=m.Journal(self.bootstrap,self.binding);journal.write('prepared',self.refs,self.observed);journal.write('merge-requested')
        self.assertEqual(self.invoke()['code'],'RULES_BOOTSTRAP_MERGED_REVIEW_RECHECKED')
        self.assertEqual(self.merges,[])

    def test_foreign_next_file_preserved_does_not_block_own_checkpoint(self):
        foreign=self.path/'.bootstrap-adoption-foreign.next';foreign.write_bytes(b'foreign')
        self.invoke();self.assertEqual(foreign.read_bytes(),b'foreign')
        self.assertEqual(list(self.path.glob('.bootstrap-adoption-*.next')),[foreign])


if __name__=='__main__':unittest.main()
