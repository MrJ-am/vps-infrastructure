import copy,unittest
import delivery_roles as R

def original():
    return {'branch_name':'main','rule_name':'main','enable_push':False,'enable_status_check':True,
        'status_check_contexts':[R.CONTEXT],'required_approvals':1,'block_on_rejected_reviews':True,
        'block_on_official_review_requests':True,'block_on_outdated_branch':True,
        'dismiss_stale_approvals':True,'apply_to_admins':True,'enable_merge_whitelist':False,
        'merge_whitelist_usernames':[],'merge_whitelist_teams':[],'enable_approvals_whitelist':False,
        'approvals_whitelist_username':[],'approvals_whitelist_teams':[],
        'protected_file_patterns':'keep-me','updated_at':'synthetic-before'}

class Roles(unittest.TestCase):
    def test_roles_cannot_change_validation_or_infrastructure(self):
        for repository in ['mrjam-validation','vps-infrastructure','../mrjam-plateforme','other']:
            with self.assertRaisesRegex(Exception,'DELIVERY_REPOSITORY_REFUSED'):R.protection_change(repository,original())
    def test_mirror_cannot_supply_required_approval_or_merge(self):
        change=R.protection_change('mrjam-plateforme',original())
        self.assertNotIn(R.ROLES['mirror'],change['merge_whitelist_usernames'])
        self.assertNotIn(R.ROLES['mirror'],change['approvals_whitelist_username'])
        self.assertNotIn(R.ROLES['review'],change['merge_whitelist_usernames'])
        self.assertNotIn(R.ROLES['merge'],change['approvals_whitelist_username'])
    def test_human_review_and_merge_remain_possible(self):
        change=R.protection_change('mrjam-plateforme',original())
        self.assertIn(R.HUMAN,change['merge_whitelist_usernames'])
        self.assertIn(R.HUMAN,change['approvals_whitelist_username'])
    def test_existing_nonstandard_restriction_is_not_expanded(self):
        value=original();value.update(enable_merge_whitelist=True,merge_whitelist_usernames=['different'])
        with self.assertRaisesRegex(Exception,'DELIVERY_EXISTING_RESTRICTION_REFUSED'):R.protection_change('vision',value)
    def test_same_restriction_can_be_reconciled(self):
        value=original();change=R.protection_change('vision',value);adopted={**value,**change}
        self.assertEqual(R.protection_change('vision',adopted),change)
        R.verify_protection(value,adopted,change)
    def test_unrelated_protection_change_is_refused(self):
        value=original();change=R.protection_change('vision',value)
        for key,replacement in [('enable_push',True),('required_approvals',0),('protected_file_patterns','')]:
            with self.assertRaisesRegex(Exception,'DELIVERY_OTHER_GATES_CHANGED'):
                R.verify_protection(value,{**value,**change,key:replacement},change)
    def test_missing_gate_is_not_silently_repaired(self):
        value=original();value['status_check_contexts']=[]
        with self.assertRaisesRegex(Exception,'DELIVERY_EXISTING_GATES_REFUSED'):R.protection_change('vision',value)
    def test_roles_have_only_write_on_the_fixed_application_repositories(self):
        account={'name':R.ROLES['mirror'],'eligible':True,'organization_memberships':0,'owned_repositories':0}
        acl=[{'owner':'MrJ-am','repo':name,'permission':2} for name in R.APPLICATIONS]
        R.verify_acl('mirror',account,acl)
        for changed in [acl+[{'owner':'MrJ-am','repo':'mrjam-validation','permission':1}],
                [{**item,'permission':3} for item in acl],acl[:-1],
                [{**item,'owner':'other'} for item in acl]]:
            with self.assertRaisesRegex(Exception,'DELIVERY_ACL_REFUSED'):R.verify_acl('mirror',account,changed)
        with self.assertRaisesRegex(Exception,'DELIVERY_ACCOUNT_REFUSED'):
            R.verify_acl('mirror',{**account,'organization_memberships':1},acl)

if __name__=='__main__':unittest.main()
