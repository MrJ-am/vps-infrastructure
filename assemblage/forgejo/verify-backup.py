#!/usr/bin/env python3
"""Restore a just-decrypted Forgejo backup in a private PostgreSQL instance."""
import datetime,hashlib,json,os,pathlib,pwd,shutil,subprocess,sys,tempfile
P=pathlib.Path

def run(args,*,input=None):
 r=subprocess.run([str(a) for a in args],input=input,capture_output=True,text=True,timeout=120)
 if r.returncode:raise RuntimeError('Isolated backup verification failed: '+P(str(args[0])).name)
 return r.stdout.strip()

def quote(v):return '"'+v.replace('"','""')+'"'

def sql(pg,socket,db,text):
 return run(['runuser','-u','postgres','--',pg/'psql','-XAtq','--set=ON_ERROR_STOP=1','--host='+str(socket),'--port='+('5432' if str(socket)=='/run/postgresql' else '55439'),'--dbname='+db],input="SET TIME ZONE 'UTC';\n"+text)

def fingerprints(pg,socket,db):
 tables=json.loads(sql(pg,socket,db,"SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public';"))
 values={}
 for table in tables:
  values[table]=sql(pg,socket,db,"SELECT encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') h FROM public."+quote(table)+" t) s;")
 return values

def main():
 snapshot,pg=map(P,sys.argv[1:]);pg=pg/'bin';os.umask(0o077)
 user=pwd.getpwnam('postgres')
 root=P(tempfile.mkdtemp(prefix='forgejo-restore-',dir='/var/lib'));os.chown(root,user.pw_uid,user.pw_gid)
 active=False
 try:
  dump=root/'forgejo.dump';shutil.copyfile(snapshot/'forgejo.dump',dump);os.chown(dump,user.pw_uid,user.pw_gid)
  run(['runuser','-u','postgres','--',pg/'initdb','-D',root/'pg','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
  run(['runuser','-u','postgres','--',pg/'pg_ctl','-D',root/'pg','-l',root/'postgres.log','-w','-t','30','-o',f'-h "" -k {root} -p 55439','start']);active=True
  sql(pg,root,'postgres','CREATE DATABASE forgejo_restore_check;')
  run(['runuser','-u','postgres','--',pg/'pg_restore','--exit-on-error','--no-owner','--no-acl','--host='+str(root),'--port=55439','--dbname=forgejo_restore_check',dump])
  # psql defaults to PGPORT; use its argument rather than a process-wide setting.
  restored=fingerprints(pg,root,'forgejo_restore_check')
  live=fingerprints(pg,P('/run/postgresql'),'forgejo')
  if restored!=live:raise RuntimeError('Restored table fingerprints differ')
  extract=snapshot/'repository-check';extract.mkdir()
  run(['tar','-xf',snapshot/'data.tar','-C',extract])
  repositories=list((extract/'forgejo/repositories').glob('*/*.git'))
  for repo in repositories:run(['git','-c','safe.directory='+str(repo),'--git-dir='+str(repo),'fsck','--full'])
  receipt={'verifiedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'isolatedPostgresqlRestore':True,'tables':len(restored),'semanticFingerprintsEqual':True,'repositoriesFsck':len(repositories),'productionDataRestored':False}
  P('/var/backup/forgejo/qualification.json').write_text(json.dumps(receipt,indent=2)+'\n')
 finally:
  if (root/'pg/postmaster.pid').exists():run(['runuser','-u','postgres','--',pg/'pg_ctl','-D',root/'pg','-m','fast','-w','stop'])
  shutil.rmtree(root)

if __name__=='__main__':main()
