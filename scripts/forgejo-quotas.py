#!/usr/bin/env python3
"""Manage native Forgejo quotas with an admin PAT read from a private file."""
import argparse,json,pathlib,re,urllib.request,urllib.error

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--url',default='https://forge.mrj.am');p.add_argument('--token-file',type=pathlib.Path,required=True)
 p.add_argument('--user',required=True);p.add_argument('--max-repositories',type=int);p.add_argument('--storage',help='Total storage, e.g. 5GiB, 500MiB, 0 or -1 (unlimited)')
 p.add_argument('--replace-quota-groups',action='store_true',help='Explicitly replace other storage quota group assignments')
 a=p.parse_args();assert re.fullmatch('[A-Za-z0-9_.-]{1,40}',a.user),'Invalid username'
 if a.max_repositories is not None:assert a.max_repositories>=-1
 token=a.token_file.read_text().strip();base=a.url.rstrip('/')+'/api/v1/'
 assert base.startswith('https://') or base.startswith('http://127.0.0.1:'),'HTTPS required'
 def api(path,data=None,method=None):
  req=urllib.request.Request(base+path,headers={'Authorization':'token '+token,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None,method=method)
  with urllib.request.urlopen(req,timeout=20) as r:return json.load(r) if r.status!=204 else None
 route='admin/users/'+a.user
 if a.storage is not None:
  match=re.fullmatch(r'(-1|[0-9]+)\s*(B|KiB|MiB|GiB|TiB)?',a.storage,re.I);assert match,'Invalid storage size'
  number=int(match[1]);factor={'b':1,'kib':1024,'mib':1024**2,'gib':1024**3,'tib':1024**4}[(match[2] or 'B').lower()]
  assert number>=0 or (number==-1 and factor==1),'Invalid unlimited quota'
  limit=number*factor;group='personal-'+a.user.lower();rule=group+'-storage'
  current=api(route+'/quota');other=[g['name'] for g in current['groups'] if g.get('name') and g['name']!=group and g['name']!='builtin-default-group']
  assert not other or a.replace_quota_groups,'Other quota groups exist; inspect them or explicitly use --replace-quota-groups'
  existing=api('admin/quota/groups')
  if not any(g['name']==group for g in existing):
   api('admin/quota/groups',{'name':group,'rules':[{'name':rule,'limit':limit,'subjects':['size:all']}]})
  else:
   found=next(g for g in existing if g['name']==group)
   assert [r['name'] for r in found['rules']]==[rule],'Existing group is not the expected personal quota group'
   api('admin/quota/rules/'+rule,{'limit':limit,'subjects':['size:all']},'PATCH')
  api(route+'/quota/groups',{'groups':[group]},'POST')
 if a.max_repositories is not None:api(route,{'max_repo_creation':a.max_repositories},'PATCH')
 result=api(route+'/quota');result['username']=a.user
 if a.max_repositories is not None:result['maxRepositories']=a.max_repositories
 print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
