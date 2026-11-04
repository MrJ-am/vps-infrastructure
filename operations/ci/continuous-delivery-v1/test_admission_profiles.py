import copy,unittest
from unittest.mock import patch
import test_admission_registry as Platform
import test_vise_admission_registry as Vise
import admission_control as A
C=Platform.C;R=Platform.R

class ProfileDispatch(unittest.TestCase):
    def setUp(self):
        self.platform=Platform.Registry();self.platform.setUp()
        fixture=Vise.ViseRegistry();fixture.setUp();self.vise=fixture.fixture
        self.vise.proposal='2'*64
        self.vise.docs['authority']['accepted_proposals']=[self.vise.proposal]
        self.vise.record['proposal_sha256']=self.vise.proposal;self.vise.refresh()
        self.vise.anchor=copy.deepcopy(self.vise.docs['authority'])
        # Fixtures reuse placeholder store names. Each mocked registry read
        # exposes the selected fixture; real filesystem/IPC qualification is
        # separate and must use distinct immutable paths.
        self.records={f.proposal:f.record for f in [self.platform,self.vise]}
        self.current=None
        def entry(proposal):
            self.current=self.platform if proposal==self.platform.proposal else self.vise
            return self.records[proposal]
        def metadata(path,maximum=131072):return self.current.files[path]
        self.anchor_paths={Platform.path('platform-anchor.json'):self.platform.anchor,
                           Platform.path('vise-anchor.json'):self.vise.anchor}
        for target,name,value in [(A,'ANCHOR_PATH',Platform.path('platform-anchor.json')),
                (A,'PROFILE','platform'),(A,'BUBBLEWRAP',Platform.path('bubblewrap')),
                (A,'EXTRA_ANCHORS',{'vise-v1':Platform.path('vise-anchor.json')})]:
            context=patch.object(target,name,value);context.start();self.addCleanup(context.stop)
        for context in [patch.object(R,'entry',side_effect=entry),
                patch.object(R,'metadata_bytes',side_effect=metadata),
                patch.object(R,'store_bytes',side_effect=lambda path:C.canonical(self.anchor_paths[path])),
                patch.object(C.time,'time',return_value=150)]:
            context.start();self.addCleanup(context.stop)

    def test_both_profiles_use_their_anchor_and_required_steps(self):
        for f in [self.platform,self.vise]:
            selected=A.load(f.proposal)
            self.assertEqual(selected['authority'],f.docs['authority'])
            steps=A.expected_steps(selected['authority'])
            self.assertEqual([s['name'] for s in steps],selected['authority']['required_steps'])
        self.assertTrue(all(set(s)=={'name','status'} for s in A.expected_steps(self.vise.docs['authority'])))

    def test_uninstalled_profile_refused_without_platform_fallback(self):
        with patch.object(A,'EXTRA_ANCHORS',{}):
            with self.assertRaisesRegex(C.Refused,'PROFILE_NOT_INSTALLED'):A.load(self.vise.proposal)
            self.assertEqual(A.load(self.platform.proposal)['authority'],self.platform.docs['authority'])

    def test_different_signing_identity_refused(self):
        self.vise.anchor['signer_uid']+=1
        with self.assertRaisesRegex(C.Refused,'PROFILE_IDENTITY_CHANGED'):A.load(self.vise.proposal)

    def test_different_daemon_recipe_refused(self):
        self.vise.anchor['producer']['collector_recipe_sha256']='f'*64
        with self.assertRaisesRegex(C.Refused,'PROFILE_RECIPE_CHANGED'):A.load(self.vise.proposal)

    def test_profile_selection_document_must_match_root_record_hash(self):
        f=self.vise;f.files[f.record['files']['details']['path']]+=b' '
        with self.assertRaisesRegex(C.Refused,'CONTENT_CHANGED'):A.load(f.proposal)

if __name__=='__main__':unittest.main()
