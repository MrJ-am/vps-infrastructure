"""Independent checks of the proposed canonical rule hook, without adoption."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(os.environ['SIGNATURE_ASSEMBLY'])
sys.path.insert(0,str(ROOT))
import policy
import runner


class RuleHook(unittest.TestCase):
    def policy(self):
        value=json.loads((ROOT/'frontend-policy-20261031.json').read_bytes())
        value['sources'].append({'id':'signature','repository':'MrJ-am/Signature',
            'revision':'1'*40,'tree_sha':'2'*40,'root':'sources/signature','tree_json':'trees/signature.json'})
        return value

    def verifier(self):
        v=runner.Verifier.__new__(runner.Verifier)
        v.sources={'signature':{'repository':'MrJ-am/Signature','revision':'1'*40}}
        v.runtime={}
        v.job=lambda _:self.fail('A refused/absent Signature profile must not create a job')
        return v

    def test_signature_source_identity_is_admitted(self):
        value=self.policy();self.assertEqual(policy.checked_frontend_policy(value),value)

    def test_observed_platform_policy_with_signature_is_admitted(self):
        value=json.loads(Path(os.environ['SIGNATURE_CURRENT_POLICY']).read_bytes())
        value['sources'].append(self.policy()['sources'][-1])
        self.assertEqual(policy.checked_policy(value),value)

    def test_other_repository_cannot_use_signature_identity(self):
        value=self.policy();value['sources'][-1]['repository']='MrJ-am/vision'
        with self.assertRaisesRegex(policy.Refused,'SIGNATURE_SOURCE_IDENTITY_REFUSED'):
            policy.checked_frontend_policy(value)

    def test_signature_cannot_hide_under_another_source_id(self):
        value=self.policy();value['sources'][-1]['id']='another-signature'
        with self.assertRaisesRegex(policy.Refused,'SIGNATURE_SOURCE_IDENTITY_REFUSED'):
            policy.checked_frontend_policy(value)

    def test_absent_signature_does_not_start_a_job(self):
        v=self.verifier();v.sources={};self.assertIsNone(v.signature())

    def test_missing_immutable_runtime_refuses_before_job(self):
        with self.assertRaisesRegex(policy.Refused,'SIGNATURE_RUNTIME_REQUIRED'):
            self.verifier().signature()

    def test_wrong_repository_refuses_before_job(self):
        v=self.verifier();v.sources['signature']['repository']='MrJ-am/vision'
        with self.assertRaisesRegex(policy.Refused,'SIGNATURE_REPOSITORY_REFUSED'):
            v.signature()


if __name__=='__main__':
    unittest.main()
