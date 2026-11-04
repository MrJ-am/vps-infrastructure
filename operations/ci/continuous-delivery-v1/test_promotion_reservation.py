import tempfile,unittest
from pathlib import Path
import test_source_observation
import promotion_reservation as R

class Reservation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.job=Path(self.tmp.name)/('a'*64);self.job.mkdir(mode=0o700);self.path=self.job/'state.json'
        self.plan={'schema_version':1,'job':'a'*64,'proposal_sha256':'b'*64,
            'old':'/nix/store/'+'c'*32+'-nixos-system-synthetic-old','new':'/nix/store/'+'d'*32+'-nixos-system-synthetic-new'}
        R.O.save(self.path,{'schema_version':1,'id':'a'*64,'phase':'validated','capture':{'proposal_sha256':'b'*64}})
    def test_reservation_durable_and_commit_only_after_both_generation_pointers(self):
        R.reserve(self.path,self.plan);self.assertEqual(R.O.read(self.path)['promotion'],R.identity(self.plan))
        with self.assertRaisesRegex(Exception,'PROMOTION_GENERATION_NOT_COMMITTED'):
            R.commit(self.path,self.plan,observe=lambda:(self.plan['new'],self.plan['old']))
        self.assertEqual(R.O.read(self.path)['phase'],'validated')
        R.commit(self.path,self.plan,observe=lambda:(self.plan['new'],)*2)
        self.assertEqual(R.O.read(self.path)['phase'],'deployed');self.assertNotIn('promotion',R.O.read(self.path))
    def test_lost_commit_response_does_not_reinsert_marker(self):
        R.reserve(self.path,self.plan);R.commit(self.path,self.plan,observe=lambda:(self.plan['new'],)*2)
        R.reserve(self.path,self.plan);R.commit(self.path,self.plan,observe=lambda:(self.plan['new'],)*2)
        self.assertNotIn('promotion',R.O.read(self.path))
    def test_another_plan_cannot_take_reservation(self):
        R.reserve(self.path,self.plan);other={**self.plan,'new':'/nix/store/'+'f'*32+'-nixos-system-other'}
        with self.assertRaisesRegex(Exception,'PROMOTION_RESERVATION_CONFLICT'):R.reserve(self.path,other)
    def test_return_requires_live_and_boot_restored_before_releasing_marker(self):
        R.reserve(self.path,self.plan)
        with self.assertRaisesRegex(Exception,'PROMOTION_RETURN_NOT_CONFIRMED'):
            R.abort(self.path,self.plan,observe=lambda:(self.plan['old'],self.plan['new']))
        R.abort(self.path,self.plan,observe=lambda:(self.plan['old'],)*2)
        self.assertEqual(R.O.read(self.path)['phase'],'validated');self.assertNotIn('promotion',R.O.read(self.path))
    def test_commit_without_reservation_is_refused(self):
        with self.assertRaisesRegex(Exception,'PROMOTION_RESERVATION_MISSING'):
            R.commit(self.path,self.plan,observe=lambda:(self.plan['new'],)*2)

if __name__=='__main__':unittest.main()
