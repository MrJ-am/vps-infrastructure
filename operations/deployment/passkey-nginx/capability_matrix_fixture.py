"""Disposable native Kanidm capabilities; all persons and tokens invented."""
import importlib.util,json,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('software_fixture',ROOT/'operations/deployment/passkey-portal/qualify.py')
Q=importlib.util.module_from_spec(spec);spec.loader.exec_module(Q)
CASES={'ordinary':[],'access_only':['idm_access_control_admins'],'service_only':['idm_service_account_admins'],
       'service_and_people':['idm_service_account_admins','idm_people_admins'],
       'identity_admin':['idm_admins'],'combined':['idm_admins','idm_access_control_admins']}

def require(value,label):
 if not value:raise RuntimeError(label)

def authenticate(f,name,key):
 code,value,session=f.request(None,'POST','/v1/auth',{'step':{'init2':{'username':name,'issue':'token','privileged':True}}})
 require(code==200,'AUTH_INIT')
 code,value,session=f.request(None,'POST','/v1/auth',{'step':{'begin':'passkey'}},session=session)
 require(code==200,'AUTH_BEGIN')
 challenge=value['state']['continue'][0]['passkey']
 code,value,_=f.request(None,'POST','/v1/auth',{'step':{'cred':{'passkey':key.assertion(challenge)}}},session=session)
 require(code==200 and 'success' in value['state'],'AUTH_ASSERT')
 return value['state']['success']

def run():
 results={}
 with Q.F['Fixture']() as f:
  identity,access=f.login('idm_admin'),f.login('admin')
  for case,groups in CASES.items():
   name='capability-'+case.replace('_','-');service='invented-'+case.replace('_','-')
   key=Q.enroll(f,identity,name)
   for group in groups:
    f.ok(access if group=='idm_access_control_admins' else identity,'POST','/v1/group/'+group+'/_attr/member',[name])
   token=authenticate(f,name,key)
   attrs=f.ok(token,'GET','/v1/self')['youare']['attrs']
   observed={g.removesuffix('@log.mrj.am') for g in attrs.get('memberof',[])}
   row={'passkey_authentication':True,'has_identity_admin': 'idm_admins' in observed,
        'has_service_admin':'idm_service_account_admins' in observed,'has_access_admin':'idm_access_control_admins' in observed}
   body={'attrs':{'name':[service],'displayname':['Invented capability matrix'],'entry_managed_by':['idm_service_account_admins']}}
   row['create_service']=f.request(token,'POST','/v1/service_account',body)[0]
   if row['create_service']!=200:f.ok(identity,'POST','/v1/service_account',body)
   code,value,_=f.request(token,'GET','/v1/service_account/'+service)
   row['read_service_visible']=code==200 and isinstance(value,dict) and value.get('attrs',{}).get('name')==[service]
   row['read_token_records']=f.request(token,'GET','/v1/service_account/'+service+'/_api_token')[0]
   row['token_before_people_role']=f.request(token,'POST','/v1/service_account/'+service+'/_api_token',
      {'label':'invented-before','expiry':int(time.time())+3600,'read_write':True,'compact':False})[0]
   for group,label,admin in (('idm_account_mail_read','grant_mail',access),('idm_people_admins','grant_people',identity)):
    code,value,_=f.request(token,'GET','/v1/group/'+group)
    row['read_'+label+'_group_members']=code==200 and isinstance(value,dict) and 'member' in value.get('attrs',{})
    row[label]=f.request(token,'POST','/v1/group/'+group+'/_attr/member',[service])[0]
    if row[label]!=200:f.ok(admin,'POST','/v1/group/'+group+'/_attr/member',[service])
   row['token_after_people_role']=f.request(token,'POST','/v1/service_account/'+service+'/_api_token',
      {'label':'invented-after','expiry':int(time.time())+3600,'read_write':True,'compact':False})[0]
   row['all_required_writes_allowed']=all(row[field]==200 for field in ('create_service','grant_mail','grant_people','token_after_people_role'))
   results[case]=row
   f.ok(token,'GET','/v1/logout')
  require(results['identity_admin']['create_service']==200 and results['identity_admin']['grant_people']==200,'IDENTITY_PRIVILEGES')
  require(results['access_only']['grant_mail']==200,'ACCESS_PRIVILEGES')
  require(results['combined']['all_required_writes_allowed'],'COMBINED_PRIVILEGES')
 return {'schema_version':1,'provider':'/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2','synthetic_only':True,
         'real_passkey_authentication':True,'actual_http_requests':True,'results':results}

if __name__=='__main__':
 try:print(json.dumps(run(),sort_keys=True))
 except Exception as error:
  print(json.dumps({'error':str(error) if isinstance(error,RuntimeError) else type(error).__name__,
    'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
  raise SystemExit(1)
