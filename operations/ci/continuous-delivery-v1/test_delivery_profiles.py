import unittest
import delivery_profiles as P
from source_snapshot import Refused


class Profiles(unittest.TestCase):
    def test_repository_identity_selects_profile_despite_candidate_hints(self):
        self.assertEqual(P.selected({'repository':'etp-vie-affective',
            'repository_id':1433178398,'target':'platform','branch':'platform/main'}),'vise')
        self.assertEqual(P.selected({'repository':'mrjam-plateforme',
            'repository_id':1437120781,'target':'vise'}),'platform')

    def test_name_alone_cannot_select_a_recipe(self):
        for identity in [None,True,'1433178398',1437120781]:
            with self.subTest(identity=identity),self.assertRaisesRegex(Refused,'REPOSITORY_REFUSED'):
                P.selected({'repository':'etp-vie-affective','repository_id':identity})

    def test_rule_and_infrastructure_repos_do_not_get_an_application_recipe(self):
        for name in ['mrjam-validation','vps-infrastructure','unknown']:
            with self.subTest(name=name),self.assertRaisesRegex(Refused,'PROJECT_RECIPE_UNAVAILABLE'):
                P.selected({'repository':name,'repository_id':1433178398})

    def test_fixed_identities_match_the_discovery_inventory(self):
        import test_intake_queue as Q
        for name,(identity,profile) in P.REPOSITORIES.items():
            self.assertEqual(identity,Q.Q.P.REPOSITORIES[name])
            self.assertIn(profile,{'platform','vise'})


if __name__=='__main__':unittest.main()
