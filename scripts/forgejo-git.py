#!/usr/bin/env python3
"""Git clone/push over HTTP(S) and SSH in the explicitly designated private test repo."""
import argparse,base64,json,os,pathlib,re,subprocess,tempfile,urllib.request

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--credentials',type=pathlib.Path,required=True)
 p.add_argument('--username',default='validation');p.add_argument('--repository',default='org-validation')
 p.add_argument('--ssh-user',default='forgejo');p.add_argument('--ssh-port',type=int,default=2222)
 p.add_argument('--known-hosts',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True)
 a=p.parse_args();base=a.url.rstrip('/');raw=a.credentials.read_text();m=re.search("generated random password is '(.*?)'",raw);password=m.group(1) if m else raw.strip()
 auth=base64.b64encode((a.username+':'+password).encode()).decode()
 def api(path,payload=None,method=None):
  req=urllib.request.Request(base+'/api/v1/'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Authorization':'Basic '+auth,'Content-Type':'application/json'},method=method)
  with urllib.request.urlopen(req,timeout=30) as r:return json.load(r) if r.status!=204 else None
 def run(args,cwd=None,env=None):
  r=subprocess.run(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
  if r.returncode:raise RuntimeError('Git validation failed: '+r.stderr[-1500:])
  return r.stdout.strip()
 repo=api(f'repos/{a.username}/{a.repository}');assert repo['private']
 with tempfile.TemporaryDirectory(prefix='forgejo-git-') as t:
  t=pathlib.Path(t);(t/'password').write_text(password);(t/'password').chmod(0o600)
  ask=t/'askpass';ask.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "$FORGEJO_TEST_USER" ;; *) cat "$FORGEJO_TEST_PASSWORD_FILE" ;; esac\n');ask.chmod(0o700)
  env=os.environ.copy();env.update(GIT_ASKPASS=str(ask),GIT_TERMINAL_PROMPT='0',FORGEJO_TEST_USER=a.username,FORGEJO_TEST_PASSWORD_FILE=str(t/'password'))
  run(['git','clone',base+f'/{a.username}/{a.repository}.git',str(t/'repo')],env=env)
  root=t/'repo';run(['git','config','user.name','Forgejo validation'],cwd=root);run(['git','config','user.email','forgejo-validation@example.org'],cwd=root)
  doc=root/'docs/git-validation.org';doc.write_text('#+TITLE: Validation Git\n* HTTPS et SSH\nDépôt privé de test. Formule : $x^2$.\n')
  run(['git','add','docs/git-validation.org'],cwd=root)
  if run(['git','status','--porcelain'],cwd=root):
   run(['git','commit','-m','Valider les opérations Git du dépôt privé'],cwd=root);run(['git','push','origin','HEAD'],cwd=root,env=env)
  head=run(['git','rev-parse','HEAD'],cwd=root)
  run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(t/'key')])
  key=api('user/keys',{'title':'org-validation-'+head[:12],'key':(t/'key.pub').read_text()})
  try:
   env['GIT_SSH_COMMAND']='ssh -i '+str(t/'key')+' -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile='+str(a.known_hosts.resolve())
   host=urllib.parse.urlsplit(base).hostname
   remote=f'ssh://{a.ssh_user}@{host}:{a.ssh_port}/{a.username}/{a.repository}.git'
   refs=run(['git','ls-remote',remote,'refs/heads/main'],env=env);assert refs.split()[0]==head
   run(['git','clone',remote,str(t/'ssh-repo')],env=env)
   run(['git','push',remote,'HEAD:refs/heads/validation-ssh'],cwd=root,env=env)
   run(['git','push',remote,':refs/heads/validation-ssh'],cwd=root,env=env)
  finally:api('user/keys/'+str(key['id']),method='DELETE')
 a.output.write_text(json.dumps({'private':True,'httpScheme':urllib.parse.urlsplit(base).scheme,'httpClonePush':True,'sshClonePush':True,'head':head,'temporaryKeyRemoved':True},indent=2)+'\n')
 print('Private repository Git clone/push over HTTP(S) and SSH passed')

if __name__=='__main__':main()
