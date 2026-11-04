import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_admission_registry as Fixture
import admission_collector as K

class CollectionProfiles(unittest.TestCase):
    def setUp(self):
        self.binding=json.loads(Path('/nix/store/d8bhnl18vsch1zbrvm28w6dvn6acz1k6-mrjam-validation-authority-policy.json').read_bytes())['producer']
        self.baseline={'rules_revision':self.binding['rules_revision']}
        context=patch.object(K.R,'anchor_for',return_value=self.baseline)
        context.start();self.addCleanup(context.stop)

    def test_baseline_and_distinct_admitted_rules(self):
        self.assertEqual(K.collection_rules(self.baseline,self.binding),self.binding['rules_revision'])
        other=copy.deepcopy(self.binding);other['rules_revision']='f'*40
        self.assertEqual(K.collection_rules(self.baseline,other),'f'*40)

    def test_unit_configuration_must_still_match_installed_baseline(self):
        other=copy.deepcopy(self.binding);other['rules_revision']='f'*40
        with self.assertRaisesRegex(K.Refused,'BASELINE_RULES_REFUSED'):
            K.collection_rules({'rules_revision':'f'*40},other)

    def test_malformed_binding_and_extra_configuration_refused(self):
        with self.assertRaises(K.Refused):K.collection_rules(self.baseline|{'profile':'vise-v1'},self.binding)
        with self.assertRaises(K.C.Refused):K.collection_rules(self.baseline,{'rules_revision':'f'*40})

if __name__=='__main__':unittest.main()
