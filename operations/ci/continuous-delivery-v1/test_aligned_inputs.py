"""Exercise the built protected verifier against the reconciled Git proposal."""
from pathlib import Path
import copy,hashlib,json,shutil,sys,tempfile,unittest
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,'/nix/store/crhzij9iqk4pya3p9l52n6kraiq3hzg0-mrjam-validate-aligned-workspace-1/lib')
import policy
from sandbox import Refused
SOURCE=ROOT/'.local/deployment-20261101/aligned-proposal-003'
GATE=Path('/nix/store/26qr08ambmn7g5dccqbr8q7aqkvcd92f-check_git_tree.py')

class Inputs(unittest.TestCase):
    def setUp(self):self.value=policy.checked_policy(policy.read_json(HERE/'aligned-policy.json'))
    def verify(self,root):return policy.verify_sources(root,self.value,GATE)
    def test_complete_git_bound_proposal(self):
        sources,digest=self.verify(SOURCE)
        self.assertEqual(len(sources),9)
        self.assertEqual(digest,'04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d')
    def test_old_graph_is_not_implicitly_adopted(self):
        altered=copy.deepcopy(self.value)
        del altered['rust_manifests']['crates/identity/Cargo.toml']
        with self.assertRaisesRegex(Refused,'RUST_GRAPH_REVIEW_REQUIRED'):policy.checked_policy(altered)
    def test_changed_lock_not_implicitly_adopted(self):
        self.value['rust_manifests']['Cargo.lock']='0'*64
        with self.assertRaisesRegex(Refused,'RUST_GRAPH_REVIEW_REQUIRED'):self.verify(SOURCE)
    def test_manifest_cannot_authorize_git_blob_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';shutil.copytree(SOURCE,root)
            target=root/'sources/platform/crates/server/src/database.rs'
            target.write_bytes(target.read_bytes()+b'\n// synthetic unauthorized change\n')
            self.rehash(root)
            with self.assertRaisesRegex(Refused,'SOURCE_BLOB_MISMATCH'):self.verify(root)
    def test_active_identity_configuration_cannot_be_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';shutil.copytree(SOURCE,root)
            (root/'sources/platform/nix/identity.nix').unlink();self.rehash(root)
            with self.assertRaisesRegex(Refused,'SOURCE_SCOPE_INCOMPLETE'):self.verify(root)
    def rehash(self,root):
        value=json.loads((root/'manifest.json').read_bytes())
        value['files']=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,
                        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in sorted(root.rglob('*')) if p.is_file() and p!=root/'manifest.json']
        (root/'manifest.json').write_text(json.dumps(value))

if __name__=='__main__':unittest.main()
