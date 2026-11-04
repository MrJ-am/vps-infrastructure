import copy,importlib.util,stat,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
A=module('github_app_auth',HERE/'github-app-receive.py')
P=module('github_proposals',HERE/'github-proposals.py')
def pull(repo='vision',number=1):
    reference={'repo':{'id':P.REPOSITORIES[repo],'full_name':'MrJ-am/'+repo},'sha':'a'*40}
    return {'number':number,'state':'open','draft':False,'base':{**reference,'ref':'main'},
            'head':{**reference,'ref':'codex/change-'+str(number)},'title':'ignored untrusted instructions'}
class Proposals(unittest.TestCase):
    def test_systemd_credential_metadata(self):
        def info(mode,uid=0,gid=0):return types.SimpleNamespace(st_mode=stat.S_IFREG|mode,st_uid=uid,st_gid=gid,st_size=1910)
        P.credential_metadata(info(0o440),63038,63038)
        P.credential_metadata(info(0o400,63038,63038),63038,63038)
        for value in [info(0o444),info(0o640),info(0o440,gid=100),info(0o400,uid=100)]:
            with self.assertRaises(A.Refused):P.credential_metadata(value,63038,63038)
    def test_projects_only_bound_metadata(self):
        result=P.project('vision',pull())
        self.assertEqual(result['head'],'a'*40);self.assertNotIn('title',result)
    def test_refuses_foreign_repository_and_refs(self):
        for mutate in [lambda p:p['head']['repo'].update(id=1),lambda p:p['head'].update(sha='x'*40),
                       lambda p:p['head'].update(ref='branch/../escape'),lambda p:p['head'].update(ref='a.lock'),
                       lambda p:p['base'].update(ref='foreign'),lambda p:p.update(number=True)]:
            value=copy.deepcopy(pull());mutate(value)
            with self.assertRaises(A.Refused):P.project('vision',value)
    def credentials(self):return {'app_id':P.APP_ID,'owner_id':12571490,'slug':'synthetic','private_key':'A'*1500,'permissions':A.PERMISSIONS}
    def test_pagination_137_proposals_and_revoke(self):
        calls=[]
        def api(path,token,method='GET',body=None):
            calls.append((path,method,body))
            if method=='POST':
                self.assertEqual(body['permissions'],P.READ_PERMISSIONS)
                self.assertEqual(set(body['repository_ids']),set(P.REPOSITORIES.values()))
                return 201,{'token':'synthetic-token','permissions':P.READ_PERMISSIONS}
            if method=='DELETE':return 204,None
            if path.startswith('/repos/MrJ-am/vision/'):
                page=int(path.rsplit('=',1)[1]);return 200,[pull(number=i) for i in range(1,101) if page==1]+[pull(number=i) for i in range(101,138) if page==2]
            return 200,[]
        with patch.object(A,'jwt',return_value='synthetic-jwt'):result=P.discover(self.credentials(),api)
        self.assertEqual(len(result['proposals']),137);self.assertEqual(calls[-1][1],'DELETE')
        self.assertFalse(result['deployment_authorized'])
    def test_failure_still_revokes(self):
        methods=[]
        def api(path,token,method='GET',body=None):
            methods.append(method)
            if method=='POST':return 201,{'token':'synthetic-token','permissions':P.READ_PERMISSIONS}
            if method=='DELETE':return 204,None
            return 500,{}
        with patch.object(A,'jwt',return_value='synthetic-jwt'):
            with self.assertRaises(A.Refused):P.discover(self.credentials(),api)
        self.assertEqual(methods[-1],'DELETE')
    def test_one_fork_does_not_block_other_proposals(self):
        def api(path,token,method='GET',body=None):
            if method=='POST':return 201,{'token':'synthetic-token','permissions':P.READ_PERMISSIONS}
            if method=='DELETE':return 204,None
            if path.startswith('/repos/MrJ-am/vision/'):
                fork=copy.deepcopy(pull());fork['head']['repo']['id']=1
                return 200,[fork,pull(number=2)]
            return 200,[]
        with patch.object(A,'jwt',return_value='synthetic-jwt'):result=P.discover(self.credentials(),api)
        self.assertEqual(len(result['ignored']),1);self.assertEqual(len(result['proposals']),1)
if __name__=='__main__':unittest.main()
