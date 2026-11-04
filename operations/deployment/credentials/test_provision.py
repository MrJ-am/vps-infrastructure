"""Synthetic tests for the closed administrative helper, no live provider."""
import copy
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

P = runpy.run_path(str(Path(__file__).with_name('provision.py')),run_name='candidate')
REFUSED = P['Refused']
TOKENS = {k:(k+'.'+('x'*48)) for k in ('identity','access','admission','cycle','replay')}


def entry(name,groups,**extra):
    return {'attrs':{'name':[name],'uuid':['3f559b41-543f-414f-9ea9-374db5003db1'],
                     'class':['object','account','service_account','memberof'],
                     'memberof':[g+'@log.mrj.am' for g in groups],**extra}}


class Files:
    def __init__(self):
        self.values = {'admission':TOKENS['admission']}
        self.writes = []
    def read(self,role):
        return self.values.get(role)
    def write(self,role,value):
        if role in self.values:
            raise REFUSED()
        self.values[role] = value
        self.writes.append(role)


class Provider:
    def __init__(self):
        self.services = {}
        self.records = {}
        self.groups = {P['MAIL']:{'unrelated-member','mrjam-admission'},P['PEOPLE']:{'idm_admins'}}
        self.mutations = []
    def __call__(self,token,method,path,body=None):
        if not P['request_permitted'](method,path,body):
            raise REFUSED()
        if method == 'GET' and path == '/v1/self':
            role = next((r for r,t in TOKENS.items() if token == t),None)
            groups = {'identity':{P['MANAGER'],'idm_admins'},'access':{P['ACCESS']},
                      'admission':{P['MAIL'],P['HIGH'],'idm_people_on_boarding','idm_all_accounts'},
                      'cycle':{P['MAIL'],'idm_all_accounts'},'replay':{P['PEOPLE'],P['HIGH'],'idm_all_accounts'}}
            if role is None:
                raise REFUSED()
            return {'youare':entry(P['SERVICES'].get(role,role),groups[role])}
        if method == 'GET' and path == '/v1/logout':
            return None
        if path.startswith('/v1/group/'):
            name = path.split('/')[3]
            if method == 'GET':
                return {'attrs':{'name':[name],'member':sorted(self.groups[name])}}
            self.mutations.append((method,path,copy.deepcopy(body)))
            self.groups[name].update(body)
            for service in self.services.values():
                if service['attrs']['name'][0] in body:
                    additions = [name+'@log.mrj.am']
                    if name == P['PEOPLE']:
                        additions.append(P['HIGH']+'@log.mrj.am')
                    service['attrs']['memberof'] = sorted(set(service['attrs']['memberof']+additions))
            return None
        if method == 'POST':
            self.mutations.append((method,path,copy.deepcopy(body)))
        if path == '/v1/service_account':
            name = body['attrs']['name'][0]
            self.services[name] = entry(name,{'idm_all_accounts'},entry_managed_by=[P['MANAGER']])
            self.records[name] = []
            return None
        name = path.split('/')[3]
        if path.endswith('/_api_token'):
            if method == 'GET':
                return copy.deepcopy(self.records[name])
            role = 'cycle' if name.endswith('cycle') else 'replay'
            self.records[name] = [{'label':P['LABEL'],'purpose':'readonly' if role == 'cycle' else 'readwrite',
                                   'expiry':body['expiry']}]
            return TOKENS[role]
        return copy.deepcopy(self.services.get(name))


class ProvisionTests(unittest.TestCase):
    def run_provision(self,api,files):
        return P['provision_workers'](api,TOKENS['identity'],TOKENS['access'],files,int(time.time()))

    def test_existing_admission_and_unrelated_members_preserved(self):
        api,files = Provider(),Files()
        result = self.run_provision(api,files)
        self.assertTrue(result['prepared'])
        self.assertEqual(files.values['admission'],TOKENS['admission'])
        self.assertEqual(files.writes,['cycle','replay'])
        self.assertEqual(api.groups[P['MAIL']],{'unrelated-member','mrjam-admission','mrjam-cycle'})
        self.assertEqual(api.groups[P['PEOPLE']],{'idm_admins','mrjam-replay'})

    def test_idempotent_no_new_tokens_or_mutations(self):
        api,files = Provider(),Files()
        self.run_provision(api,files)
        old = copy.deepcopy(api.mutations)
        self.run_provision(api,files)
        self.assertEqual(api.mutations,old)
        self.assertEqual(files.writes,['cycle','replay'])

    def test_conflicting_existing_service_fails_before_any_write(self):
        for field,value in [('entry_managed_by',['other']),('class',['person','account','object']),
                            ('memberof',[P['PEOPLE']]),('mail',['invented@example.invalid']),
                            ('account_expire',['2030-01-01T00:00:00Z'])]:
            with self.subTest(field=field):
                api,files = Provider(),Files()
                api.services['mrjam-cycle'] = entry('mrjam-cycle',{'idm_all_accounts'},entry_managed_by=[P['MANAGER']])
                api.services['mrjam-cycle']['attrs'][field] = value
                api.records['mrjam-cycle'] = []
                with self.assertRaises(REFUSED): self.run_provision(api,files)
                self.assertEqual(api.mutations,[])
                self.assertEqual(files.writes,[])

    def test_orphan_issuance_is_not_rotated_or_duplicated(self):
        api,files = Provider(),Files()
        self.run_provision(api,files)
        del files.values['cycle']
        api.mutations.clear()
        with self.assertRaises(REFUSED): self.run_provision(api,files)
        self.assertEqual(api.mutations,[])

    def test_wrong_purpose_or_expiry_is_refused(self):
        for key,value in [('purpose','readwrite'),('expiry',None),('expiry',int(time.time())-1),('label','unrelated')]:
            api,files = Provider(),Files()
            self.run_provision(api,files)
            api.records['mrjam-cycle'][0][key] = value
            api.mutations.clear()
            with self.assertRaises(REFUSED): self.run_provision(api,files)
            self.assertEqual(api.mutations,[])

    def test_missing_privilege_and_admission_stop_before_mutation(self):
        api,files = Provider(),Files()
        with self.assertRaises(REFUSED):
            P['provision_workers'](api,TOKENS['admission'],TOKENS['access'],files,int(time.time()))
        del files.values['admission']
        with self.assertRaises(REFUSED): self.run_provision(api,files)
        self.assertEqual(api.mutations,[])

    def test_no_reset_group_creation_or_arbitrary_request(self):
        for method,path,body in [('DELETE','/v1/person/invented',None),
                ('POST','/v1/group',{'attrs':{'name':['arbitrary']}}),
                ('POST','/v1/raw/modify',{}),('GET','/v1/person',None),
                ('GET','/v1/self/_uat',None),('POST','/v1/service_account',{'attrs':{'name':['arbitrary']}}),
                ('POST','/v1/group/'+P['PEOPLE']+'/_attr/member',['mrjam-cycle']),
                ('GET','https://evil.invalid/v1/self',None)]:
            self.assertFalse(P['request_permitted'](method,path,body))
        self.assertFalse(P['request_permitted']('POST','/v1/service_account/mrjam-cycle/_api_token',
            {'label':P['LABEL'],'expiry':int(time.time())+86400,'read_write':True,'compact':False}))

    def test_dedicated_cli_cache_only(self):
        good = {'instances':{'':{'keys':{},'tokens':{'invented@log.mrj.am':TOKENS['identity']}}}}
        self.assertEqual(P['cache_token'](json.dumps(good).encode()),TOKENS['identity'])
        duplicate = json.dumps(good).replace('"instances":','"instances":{},"instances":',1)
        with self.assertRaises(REFUSED): P['cache_token'](duplicate.encode())
        for changed in [ {'instances':{'other':good['instances']['']}},
                         {'instances':{'':{'keys':{},'tokens':{'one@log.mrj.am':TOKENS['identity'],'two@log.mrj.am':TOKENS['access']}}}},
                         {'instances':{'':{'keys':{},'tokens':{'invented@evil.invalid':TOKENS['identity']}}}} ]:
            with self.assertRaises(REFUSED): P['cache_token'](json.dumps(changed).encode())

    def test_privilege_hint_never_requests_reauth_for_active_static_session(self):
        for expiry,expected in [(int(time.time())+3600,False),(int(time.time())+30,True),(None,True)]:
            payload = base64.urlsafe_b64encode(json.dumps({'purpose':{'readwrite':{'expiry':expiry}}}).encode()).decode().rstrip('=')
            token = 'synthetic.'+payload+'.signature'
            cache = {'instances':{'':{'keys':{},'tokens':{'invented@log.mrj.am':token}}}}
            self.assertEqual(P['needs_reauth'](json.dumps(cache).encode()),expected)

    def test_atomic_files_private_no_overwrite_and_no_admission_write(self):
        with tempfile.TemporaryDirectory() as directory:
            files = P['TokenFiles'].__new__(P['TokenFiles'])
            files.fd = P['H']['open_directory'](Path(directory))
            try:
                files.write('cycle',TOKENS['cycle'])
                path = Path(directory)/'kanidm-cycle.token'
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
                self.assertEqual(path.stat().st_nlink,1)
                self.assertEqual(files.read('cycle'),TOKENS['cycle'])
                before = path.read_bytes()
                with self.assertRaises(FileExistsError): files.write('cycle',TOKENS['access'])
                self.assertEqual(path.read_bytes(),before)
                with self.assertRaises(REFUSED): files.write('admission',TOKENS['access'])
            finally:
                os.close(files.fd)

    def test_symlink_and_group_readable_existing_token_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root/'private'
            private.write_text(TOKENS['cycle'])
            private.chmod(0o600)
            path = root/'kanidm-cycle.token'
            path.symlink_to(private)
            files = P['TokenFiles'].__new__(P['TokenFiles'])
            files.fd = P['H']['open_directory'](root)
            try:
                with self.assertRaises(OSError): files.read('cycle')
                path.unlink(); path.write_text(TOKENS['cycle']); path.chmod(0o640)
                with self.assertRaises(REFUSED): files.read('cycle')
            finally:
                os.close(files.fd)

    def test_main_error_is_closed(self):
        output = io.StringIO()
        with patch.object(os,'geteuid',return_value=12345),patch('signal.alarm'),contextlib.redirect_stderr(output):
            self.assertEqual(P['main'](),1)
        self.assertEqual(output.getvalue(),'{"error":"KANIDM_WORKER_PROVISION_REFUSED"}\n')

    def test_root_administrative_credential_uses_exact_systemd_readonly_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'identity-session'
            path.write_bytes(b'INVENTED-CACHE')
            path.chmod(0o400)
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            real_fstat=os.fstat
            def root_metadata(descriptor):
                value=real_fstat(descriptor)
                return SimpleNamespace(st_uid=0,st_gid=0,st_mode=value.st_mode,st_nlink=value.st_nlink,
                    st_size=value.st_size,st_mtime_ns=value.st_mtime_ns,st_ctime_ns=value.st_ctime_ns)
            try:
                with patch.object(os,'fstat',side_effect=root_metadata),patch.object(os,'fstatvfs',return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
                    self.assertEqual(P['administrative_cache'](fd,'identity-session'),b'INVENTED-CACHE')
                    for mode in (0o440,0o600,0o640,0o444,0o000):
                        path.chmod(mode)
                        with self.assertRaises((REFUSED,PermissionError)):
                            P['administrative_cache'](fd,'identity-session')
                    path.chmod(0o400)
                    with self.assertRaises(REFUSED):
                        P['administrative_cache'](fd,'arbitrary')
            finally:
                os.close(fd)

    def test_root_administrative_credential_refuses_mutability_links_and_wrong_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'identity-session'
            path.write_bytes(b'INVENTED-CACHE');path.chmod(0o400)
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            real_fstat=os.fstat
            def metadata(descriptor,**changes):
                value=real_fstat(descriptor)
                fields=dict(st_uid=0,st_gid=0,st_mode=value.st_mode,st_nlink=value.st_nlink,
                    st_size=value.st_size,st_mtime_ns=value.st_mtime_ns,st_ctime_ns=value.st_ctime_ns)
                return SimpleNamespace(**(fields|changes))
            try:
                with patch.object(os,'fstat',side_effect=metadata),patch.object(os,'fstatvfs',return_value=SimpleNamespace(f_flag=0)):
                    with self.assertRaises(REFUSED): P['administrative_cache'](fd,'identity-session')
                for changes in ({'st_uid':948},{'st_gid':944},{'st_nlink':2},{'st_size':0},{'st_size':65537}):
                    with patch.object(os,'fstat',side_effect=lambda descriptor:metadata(descriptor,**changes)),patch.object(os,'fstatvfs',return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
                        with self.assertRaises(REFUSED): P['administrative_cache'](fd,'identity-session')
                path.rename(Path(directory)/'elsewhere')
                path.symlink_to(Path(directory)/'elsewhere')
                with self.assertRaises(OSError): P['administrative_cache'](fd,'identity-session')
            finally:
                os.close(fd)

    def test_human_entry_requires_real_terminal_and_never_echoes_data(self):
        human = runpy.run_path(str(Path(__file__).with_name('human_login.py')),run_name='human')
        output = io.StringIO()
        with patch.object(os,'isatty',return_value=False),contextlib.redirect_stderr(output):
            self.assertEqual(human['main'](),1)
        self.assertEqual(output.getvalue(),'HUMAN_TERMINAL_REQUIRED\n')


if __name__ == '__main__': unittest.main()
