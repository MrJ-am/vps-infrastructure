#!/usr/bin/env python3
"""Transport of a fixed, reviewable Forgejo payload through the existing SSH channel."""
import io,json,os,pathlib,re,shlex,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
NIXPKGS=json.loads((ROOT/'assemblage/manifest.json').read_text())['toolchain']['production']['nixpkgs']

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 phase=os.environ['MRJAM_OPERATION'].removeprefix('forgejo-')
 assert phase in ('preparer','deployer','retour','tester','persistance')
 revision=json.loads((ROOT/'operations/forgejo-candidat.json').read_text())['revision_sources'];assert re.fullmatch('[0-9a-f]{40}',revision)
 remote='/root/mrjam-corrections/forgejo/'+revision
 if phase!='retour':
  subprocess.run(['git','fetch','--depth=1','origin',revision],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
  listing=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'assemblage/forgejo'],cwd=ROOT,text=True).splitlines()
  data=io.BytesIO()
  with tarfile.open(fileobj=data,mode='w:gz') as t:
   for path in listing+['scripts/monolithe-sauvegarde.py']:
    if path.endswith(('.nix','.json','.js','.css','.tmpl','.py','.org','.png')):
     content=subprocess.check_output(['git','show',revision+':'+path],cwd=ROOT)
     name='payload/backup-existing.py' if path.startswith('scripts/') else 'payload/'+path.removeprefix('assemblage/forgejo/')
     info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o600
     t.addfile(info,io.BytesIO(content))
  command='umask 077; mkdir -p '+remote+'; tar -xzf - -C '+remote
  subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),command],input=data.getvalue(),check=True)
 if phase in ('tester','persistance'):
  import base64,tempfile
  script=remote+'/payload/qualification.py'
  action='seed' if phase=='tester' else 'persistance'
  command='nix-shell -I nixpkgs='+NIXPKGS+' -p python3 --run '+shlex.quote('python3 -B '+script+' '+action+' '+revision)
  result=subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),command],capture_output=True,text=True)
  if result.returncode:
   # No stdout: it may contain a newly generated test credential.
   raise RuntimeError('Qualification distante refusée: '+result.stderr[-1800:])
  value=json.loads(result.stdout)
  if phase=='persistance':
   print(json.dumps(value));return
  password=value.pop('password')
  cipher=subprocess.run(['openssl','pkeyutl','-encrypt','-pubin','-inkey',str(ROOT/'operations/forgejo-validation-recipient.pub'),'-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256'],input=json.dumps({'username':value['username'],'password':password}).encode(),capture_output=True,check=True).stdout
  with tempfile.TemporaryDirectory(prefix='forgejo-qualification-') as t:
   t=pathlib.Path(t);pw=t/'password';pw.write_text(password);pw.chmod(0o600)
   known=t/'known_hosts';known.write_text(value['knownHosts'])
   gitcheck=t/'git.py';gitcheck.write_bytes(subprocess.check_output(['git','show',revision+':scripts/forgejo-git.py'],cwd=ROOT))
   r=subprocess.run(['python3',str(gitcheck),'--url','https://forge.mrj.am','--username',value['username'],'--credentials',str(pw),'--known-hosts',str(known),'--output',str(t/'git-result.json')],capture_output=True,text=True)
   if r.returncode:raise RuntimeError('Git HTTPS/SSH production refusé: '+r.stderr[-1800:])
   value['git']=json.loads((t/'git-result.json').read_text())
  value['validationCredentialsEncrypted']=base64.b64encode(cipher).decode()
  print(json.dumps(value));return
 command='nix-shell -I nixpkgs='+NIXPKGS+' -p python3 --run '+shlex.quote('python3 -B '+remote+'/payload/promouvoir.py '+phase+' '+revision)
 subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),command],check=True)

if __name__=='__main__':main()
