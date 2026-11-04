import copy,unittest
from unittest.mock import patch
import test_source_observation
import test_delivery_roles as T
import forge_proposal as M

class Mirror(unittest.TestCase):
    def setUp(self):
        self.p={'repository':'mrjam-plateforme','repository_id':1437120781,'number':3,
            'draft':False,'branch':'synthetic','base':'a'*40,'head':'b'*40}
        self.branch=M.branch_name(self.p);self.head=None;self.main='a'*40;self.posts=0;self.pushes=0;self.pr=None
        self.protection=T.original();self.protection.update(M.R.protection_change('mrjam-plateforme',self.protection))
        self.repo={'id':8,'full_name':'MrJ-am/mrjam-plateforme','private':True,'has_actions':False,'default_branch':'main'}
    def request(self,method,path,body=None):
        if path=='':return self.repo
        if path=='/branch_protections/main':return copy.deepcopy(self.protection)
        if path=='/branches/main':return {'commit':{'id':self.main}}
        if path=='/branches/'+self.branch:return {'commit':{'id':self.head}} if self.head else None
        if method=='GET':return [self.pr] if self.pr else []
        self.assertEqual((method,path),('POST','/pulls'));self.assertEqual(body['head'],self.branch)
        self.posts+=1;self.pr={'number':2,'state':'open','merged':False,'head':{'ref':self.branch,'sha':self.head},
            'base':{'ref':'main'},'user':{'login':M.R.ROLES['mirror']}};return self.pr
    def push(self,branch):self.assertEqual(branch,self.branch);self.pushes+=1;self.head=self.p['head']
    def mirror(self):return M.mirror(self.p,'c'*64,5,self.request,self.push)
    def test_receives_exact_branch_without_review_merge_or_main_write(self):
        result=self.mirror();self.assertEqual(result['head'],'b'*40);self.assertEqual(self.main,'a'*40)
        self.assertFalse(result['reviewed']);self.assertFalse(result['merged']);self.assertEqual(self.posts,1)
    def test_lost_result_reconciles_existing_branch_and_pull(self):
        self.mirror();self.mirror();self.assertEqual((self.pushes,self.posts),(1,1))
    def test_colliding_branch_never_overwritten(self):
        self.head='d'*40
        with self.assertRaisesRegex(Exception,'MIRROR_BRANCH_COLLISION'):self.mirror()
        self.assertEqual((self.pushes,self.posts),(0,0))
    def test_main_moved_before_push_is_refused(self):
        self.main='e'*40
        with self.assertRaisesRegex(Exception,'MIRROR_BASE_MOVED'):self.mirror()
        self.assertEqual(self.pushes,0)
    def test_main_moved_during_push_does_not_create_pull(self):
        original=self.push
        def moved(branch):original(branch);self.main='e'*40
        self.push=moved
        with self.assertRaisesRegex(Exception,'MIRROR_BASE_MOVED'):self.mirror()
        self.assertEqual(self.posts,0)
    def test_wrong_repo_or_enabled_actions_never_receives_candidate(self):
        for key,value in [('id',999),('private',False),('has_actions',True)]:
            original=copy.deepcopy(self.repo);self.repo[key]=value
            with self.assertRaisesRegex(Exception,'MIRROR_REPOSITORY_REFUSED'):self.mirror()
            self.repo=original
        self.assertEqual(self.pushes,0)
    def test_missing_separation_is_refused(self):
        self.protection=T.original()
        with self.assertRaisesRegex(Exception,'DELIVERY_RESTRICTION_NOT_ADOPTED'):self.mirror()
        self.assertEqual(self.pushes,0)
    def test_another_author_cannot_supply_reception_receipt(self):
        self.mirror();self.pr['user']['login']='another'
        with self.assertRaisesRegex(Exception,'MIRROR_PULL_COLLISION'):self.mirror()
    def test_closed_pull_is_not_reopened_implicitly(self):
        self.mirror();self.pr['state']='closed'
        with self.assertRaisesRegex(Exception,'MIRROR_PULL_ALREADY_CLOSED'):self.mirror()
    def test_only_forge_origin_receives_push_credential(self):
        env=M.git_environment('synthetic-token')
        settings={env['GIT_CONFIG_KEY_'+str(i)]:env['GIT_CONFIG_VALUE_'+str(i)] for i in range(int(env['GIT_CONFIG_COUNT']))}
        self.assertNotIn('http.https://github.com/.extraHeader',settings)
        self.assertIn('http.https://forge.mrj.am/.extraHeader',settings)
        self.assertEqual(settings['core.hooksPath'],'/dev/null');self.assertEqual(settings['http.followRedirects'],'false')
    def test_api_cannot_review_merge_change_protections_or_read_arbitrary_content(self):
        api=M.API('mrjam-plateforme',self.branch,'synthetic-mirror','synthetic-reader')
        with patch.object(M.http.client,'HTTPConnection') as connection:
            for method,path,body in [('POST','/pulls/1/merge',{}),('POST','/pulls/1/reviews',{}),
                    ('PATCH','/branch_protections/main',{}),('GET','/contents/private',None)]:
                with self.assertRaisesRegex(Exception,'MIRROR_API_ROUTE_REFUSED'):api(method,path,body)
            connection.assert_not_called()

if __name__=='__main__':unittest.main()
