import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_promotion_service
import acceptance_service as S

class Routing(unittest.TestCase):
    def setUp(self):
        self.job={'capture':{'proposal':{'repository':'mrjam-plateforme','repository_id':1437120781}}}
        self.state=Path('/synthetic/state');self.jobs=Path('/synthetic/jobs');self.verify=Mock()
    def check(self):return S.staging_check(self.state,self.jobs,self.job,self.verify)
    def vise(self):self.job['capture']['proposal']={'repository':'etp-vie-affective','repository_id':1433178398}
    def test_platform_retains_live_staging_gate(self):
        with patch.object(S.T,'ready',return_value='platform') as gate:
            self.assertEqual(self.check(),'platform');gate.assert_called_once_with(Path('/var/lib/mrjam-staging'),self.job)
    def test_disabled_vise_refused_without_using_platform_gate(self):
        self.vise()
        with patch.object(S.T,'ready') as gate:
            with self.assertRaisesRegex(Exception,'ACCEPTANCE_PROFILE_NOT_INSTALLED'):self.check()
            gate.assert_not_called()
    def test_enabled_vise_passes_installed_recipe_and_fresh_verifier(self):
        self.vise();gate=Mock();gate.ready.return_value='vise'
        with patch.object(S,'ENABLE_VISE',True),patch.object(S,'RECIPE','/fixed/recipe'),\
                patch.dict('sys.modules',{'acceptance_gate':gate}),patch.object(S.T,'ready') as platform:
            self.assertEqual(self.check(),'vise');platform.assert_not_called()
        self.assertEqual(gate.ready.call_args.args[-1],self.verify)
        self.assertEqual(gate.ready.call_args.kwargs['recipe'],Path('/fixed/recipe/operations/vise/delivery/generations.nix'))
    def test_wrong_repository_id_refused_before_any_gate(self):
        self.vise();self.job['capture']['proposal']['repository_id']=1
        with patch.object(S.T,'ready') as gate:
            with self.assertRaisesRegex(Exception,'DELIVERY_PROFILE_REPOSITORY_REFUSED'):self.check()
            gate.assert_not_called()

if __name__=='__main__':unittest.main()
