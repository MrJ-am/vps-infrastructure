import copy,hashlib,json,unittest
import host_views as V

class Views(unittest.TestCase):
    def setUp(self):
        p=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.path=p('candidate');self.state={'system':p('old'),'adopted':p('platform')}
        self.raw=json.dumps(self.state).encode()
        old={'schema_version':1,'profile':'vise-v1','phase':'current','candidatePath':self.path,
            'input_state_sha256':hashlib.sha256(self.raw).hexdigest(),'system':p('old'),
            'assertions_pass':True,'no_implicit_restart':True,'backup_enabled':True,
            'units':{'vise.service':'a'*64,'postgresql.service':'b'*64},
            'platform_adopted':p('platform'),'artifact':p('old-artifact'),'adopted':None,
            **dict.fromkeys(['routes','identity_limits','environment','preflight','boot'],'c'*64)}
        new=copy.deepcopy(old);new.update(phase='candidate',system=p('new'),artifact=p('new-artifact'),adopted=p('new-adopted'))
        new['units']['vise.service']='d'*64
        self.views={'current':old,'candidate':new}
        self.candidate={'schema_version':2,'profile':'vise-v1','bundle':new['artifact'],'adopted':new['adopted'],'deployment_authorized':False}
    def verify(self):return V.verify(self.views,self.raw,self.path,self.candidate)
    def test_exact_views(self):self.assertEqual(self.verify()['changed'],['vise.service'])
    def test_each_preservation_gate_refuses_change(self):
        for name in ['routes','platform_adopted','identity_limits','environment','preflight','boot']:
            with self.subTest(name=name):
                old=self.views['candidate'][name];self.views['candidate'][name]='f'*64
                with self.assertRaises(ValueError):self.verify()
                self.views['candidate'][name]=old
    def test_other_service_change_refused(self):
        self.views['candidate']['units']['postgresql.service']='f'*64
        with self.assertRaises(ValueError):self.verify()
    def test_wrong_current_or_candidate_refused(self):
        self.views['current']['system']=self.views['candidate']['system']
        with self.assertRaises(ValueError):self.verify()
    def test_assertions_backup_and_restart_gates_cannot_be_faked(self):
        for name in ['assertions_pass','no_implicit_restart','backup_enabled']:
            for bad in (False,1):
                self.views['candidate'][name]=bad
                with self.assertRaises(ValueError):self.verify()
            self.views['candidate'][name]=True
    def test_cross_job_or_phase_views_refused(self):
        self.views['candidate']['input_state_sha256']='f'*64
        with self.assertRaises(ValueError):self.verify()

if __name__=='__main__':unittest.main()
