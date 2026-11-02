"""Exact fixed worker API sequence using one invented idm_admins-only person."""
import importlib.util,json,runpy,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('capability_matrix_fixture.py'))
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
Q=M.Q
P=runpy.run_path('/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2/libexec/provision.py',run_name='immutable_v2')

def run():
 with Q.F['Fixture']() as f:
  identity,access=f.login('idm_admin'),f.login('admin')
  key=Q.enroll(f,identity,'invented-idm-person')
  f.ok(identity,'POST','/v1/group/idm_admins/_attr/member',['invented-idm-person'])
  token=M.authenticate(f,'invented-idm-person',key)
  observed=P['members'](P['self_attrs'](f.ok(token,'GET','/v1/self')),'memberof')
  M.require({'idm_admins','idm_group_admins','idm_service_account_admins'}<=observed and 'idm_access_control_admins' not in observed,'EXACT_PERSON_ROLES')
  f.ok(identity,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
  f.ok(identity,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
  f.ok(access,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
  admission=f.ok(identity,'POST','/v1/service_account/mrjam-admission/_api_token',{'label':'invented-existing','expiry':int(time.time())+86400,'read_write':True})
  files=Q.F['MemoryFiles'](admission)
  legacy=P['Api'](f.context,port=f.port)
  try:P['provision_workers'](legacy,token,token,files,int(time.time()))
  except P['Refused']:pass
  else:raise RuntimeError('OLD_GATE_UNEXPECTEDLY_ACCEPTED')
  M.require(legacy.last_failure is None and legacy.count==2 and files.writes==[],'OLD_GATE_NOT_CAUSE')
  api=P['Api'](f.context,port=f.port)
  before={group:P['members'](P['attrs'](api(token,'GET','/v1/group/'+group)),'member') for group in (P['MAIL'],P['PEOPLE'])}
  ownership={group:sorted(P['members'](P['attrs'](api(token,'GET','/v1/group/'+group)),'entry_managed_by')) for group in (P['MAIL'],P['PEOPLE'])}
  M.require(P['token_identity'](api,admission,'admission'),'ADMISSION_VALID')
  for role in ('cycle','replay'):
   M.require(P['service'](api,token,role) is None,'FRESH_FIXED_SERVICE_REQUIRED')
   api(token,'POST','/v1/service_account',{'attrs':{'name':[P['SERVICES'][role]],'displayname':['Mrjam '+role+' worker'],'entry_managed_by':[P['MANAGER']]}})
   M.require(P['service'](api,token,role) is not None,'FIXED_SERVICE_NOT_CREATED')
   group=P['MAIL'] if role=='cycle' else P['PEOPLE']
   api(token,'POST','/v1/group/'+group+'/_attr/member',[P['SERVICES'][role]])
   after=P['members'](P['attrs'](api(token,'GET','/v1/group/'+group)),'member')
   M.require(after==before[group]|{P['SERVICES'][role]},'OTHER_MEMBER_CHANGED')
   issued=api(token,'POST','/v1/service_account/'+P['SERVICES'][role]+'/_api_token',{'label':P['LABEL'],'expiry':int(time.time())+90*86400,'read_write':role=='replay','compact':False})
   files.write(role,issued)
   M.require(P['token_identity'](api,issued,role),'FIXED_TOKEN_INVALID')
  M.require(files.read('admission')==admission and len(set(files.values.values()))==3,'ADMISSION_OR_DISTINCTNESS')
  # This lower-scope second person can manage the low-privilege MAIL group,
  # but cannot alter the privileged PEOPLE group.
  group_key=Q.enroll(f,identity,'invented-group-person')
  f.ok(identity,'POST','/v1/group/idm_group_admins/_attr/member',['invented-group-person'])
  group_token=M.authenticate(f,'invented-group-person',group_key)
  group_attrs=P['self_attrs'](f.ok(group_token,'GET','/v1/self'))
  group_memberships=P['members'](group_attrs,'memberof')
  M.require('idm_group_admins' in group_memberships and 'idm_admins' not in group_memberships and 'idm_access_control_admins' not in group_memberships,'GROUP_ONLY_ROLES')
  group_before={group:P['members'](P['attrs'](api(token,'GET','/v1/group/'+group)),'member') for group in (P['MAIL'],P['PEOPLE'])}
  M.require(all('invented-group-person' not in members for members in group_before.values()),'GROUP_TARGET_NOT_NEW')
  mail_status=f.request(group_token,'POST','/v1/group/'+P['MAIL']+'/_attr/member',['invented-group-person'])[0]
  people_status=f.request(group_token,'POST','/v1/group/'+P['PEOPLE']+'/_attr/member',['invented-group-person'])[0]
  group_after={group:P['members'](P['attrs'](api(token,'GET','/v1/group/'+group)),'member') for group in (P['MAIL'],P['PEOPLE'])}
  M.require(mail_status==200 and group_after[P['MAIL']]==group_before[P['MAIL']]|{'invented-group-person'},'GROUP_MAIL_ADDITION')
  M.require(people_status==404 and group_after[P['PEOPLE']]==group_before[P['PEOPLE']],'GROUP_PEOPLE_CHANGED')
  f.ok(group_token,'GET','/v1/logout');f.ok(token,'GET','/v1/logout')
  return {'schema_version':1,'synthetic_only':True,'provider':'Kanidm 1.11.2',
    'idm_admins_only_person_authenticated':True,'identity_service_and_group_memberships':True,'access_control_membership':False,
    'unchanged_v2_rejected_only_its_membership_gate':True,'v2_gate_native_failures':False,'v2_gate_requests':legacy.count,
    'same_person_exact_fixed_worker_requests_succeeded':True,'native_token_scopes_exact':True,'admission_preserved':True,
    'membership_targets_preserved':True,'fixed_group_entry_managers':ownership,
    'group_admin_only_second_person':{'mail_post_status':mail_status,'people_post_status':people_status,'new_mail_member_observed':True,'other_members_preserved':True,'people_group_unchanged':True},
    'sessions_revoked':True}

if __name__=='__main__':
 try:print(json.dumps(run(),sort_keys=True))
 except Exception as error:
  print(json.dumps({'error':str(error) if isinstance(error,RuntimeError) else type(error).__name__,
   'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
  raise SystemExit(1)
