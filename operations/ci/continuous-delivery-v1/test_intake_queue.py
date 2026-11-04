import importlib.util,subprocess,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
for name,filename in [('github_app_auth','github-app-receive.py'),('github_proposals','github-proposals.py')]:
    s=importlib.util.spec_from_file_location(name,HERE/filename);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m)
import intake_queue as Q
def proposal(number=1,head='b'*40,draft=False,repository='mrjam-plateforme'):
    return {'repository':repository,'repository_id':Q.P.REPOSITORIES[repository],'number':number,
        'draft':draft,'base':'a'*40,'head':head,'branch':'synthetic/'+str(number)}
class Scheduling(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.q=Q.Queue(self.root);self.addCleanup(self.q.close)
    def test_idempotency_and_ready_survives_closure(self):
        p=proposal();self.q.observe([p],10);self.q.observe([p],11)
        claim=self.q.claim(12);self.assertIsNone(self.q.claim(13))
        self.q.finish(claim,14,receipt='d'*64);self.q.observe([],15)
        self.assertEqual(self.q.ready()[0]['visible'],0)
        with self.assertRaisesRegex(Q.S.Refused,'QUEUE_ACK_REFUSED'):self.q.acknowledge(claim['key'],'e'*64,16)
        self.q.acknowledge(claim['key'],'d'*64,16);self.q.acknowledge(claim['key'],'d'*64,17)
        self.assertEqual(self.q.ready(),[]);self.q.observe([p],18);self.assertIsNone(self.q.claim(19))
    def test_concurrent_connections_and_expired_lease_recovery(self):
        self.q.observe([proposal()],10);old=self.q.claim(11,lease_seconds=3)
        other=Q.Queue(self.root)
        try:
            self.assertIsNone(other.claim(12));new=other.claim(14)
            self.assertNotEqual(old['lease'],new['lease']);self.assertEqual(new['attempt'],2)
            with self.assertRaisesRegex(Q.S.Refused,'QUEUE_STALE_LEASE'):self.q.finish(old,15,receipt='d'*64)
            other.finish(new,15,receipt='e'*64)
        finally:other.close()
        self.assertEqual(self.q.ready()[0]['receipt'],'e'*64)
    def test_failure_does_not_block_another_project(self):
        first=proposal(repository='etp-vie-affective');second=proposal(2,repository='vision')
        self.q.observe([first],1);bad=self.q.claim(2);self.q.finish(bad,3,code='RECIPE_NOT_READY',retry_seconds=300)
        self.q.observe([first,second],4);good=self.q.claim(5);self.assertEqual(good['proposal'],second)
        self.q.finish(good,6,receipt='e'*64);self.assertIsNone(self.q.claim(7))
        self.assertEqual(self.q.claim(303)['key'],bad['key'])
    def test_new_head_never_reuses_receipt(self):
        self.q.observe([proposal()],1);old=self.q.claim(2);self.q.finish(old,3,receipt='d'*64)
        replacement=proposal(head='c'*40);self.q.observe([replacement],4);new=self.q.claim(5)
        self.assertNotEqual(old['key'],new['key']);self.assertEqual(new['proposal'],replacement)
    def test_draft_or_disappeared_proposal_not_claimed(self):
        self.q.observe([proposal(draft=True)],1);self.assertIsNone(self.q.claim(2))
        self.q.observe([proposal()],3);self.q.observe([],4);self.assertIsNone(self.q.claim(5))
    def test_invalid_snapshot_does_not_hide_existing_jobs(self):
        self.q.observe([proposal()],1)
        with self.assertRaisesRegex(Q.S.Refused,'QUEUE_DUPLICATE_OBSERVATION'):self.q.observe([proposal(),proposal(head='c'*40)],2)
        self.assertIsNotNone(self.q.claim(3))
    def test_modes_and_symlink_refusal(self):
        self.q.observe([proposal()],1)
        for p in self.root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        other=self.root/'other';other.mkdir(mode=0o700);(other/'intake.sqlite').symlink_to(self.root/'intake.sqlite')
        with self.assertRaisesRegex(Q.S.Refused,'QUEUE_FILE_REFUSED'):Q.Queue(other)
    def test_diagnostics_are_closed_codes(self):
        self.q.observe([proposal()],1);claim=self.q.claim(2)
        with self.assertRaisesRegex(Q.S.Refused,'QUEUE_CODE_REFUSED'):self.q.finish(claim,3,code='untrusted secret text')
        self.q.finish(claim,4,code='SOURCE_REFUSED')
    def test_process_exit_without_sqlite_close_preserves_claim_for_recovery(self):
        self.q.observe([proposal()],1)
        child="import os,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport test_intake_queue as T\nq=T.Q.Queue(Path(sys.argv[2]))\nassert q.claim(2,lease_seconds=2) is not None\nos._exit(0)\n"
        subprocess.run([sys.executable,'-I','-S','-',str(HERE),str(self.root)],input=child.encode(),check=True,capture_output=True,timeout=10)
        self.assertIsNone(self.q.claim(3))
        recovered=self.q.claim(4);self.assertEqual(recovered['attempt'],2)
        self.q.finish(recovered,5,receipt='e'*64)
        self.assertEqual(self.q.ready()[0]['receipt'],'e'*64)
if __name__=='__main__':unittest.main()
