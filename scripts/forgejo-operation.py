#!/usr/bin/env python3
"""Transport of a fixed, reviewable Forgejo payload through the existing SSH channel."""
import io,json,os,pathlib,re,shlex,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
NIXPKGS=json.loads((ROOT/'assemblage/manifest.json').read_text())['toolchain']['production']['nixpkgs']

def main():
 assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 phase=os.environ['MRJAM_OPERATION'].removeprefix('forgejo-')
 assert phase in ('preparer','deployer','retour')
 revision=json.loads((ROOT/'operations/forgejo-candidat.json').read_text())['revision_sources'];assert re.fullmatch('[0-9a-f]{40}',revision)
 remote='/root/mrjam-corrections/forgejo/'+revision
 if phase!='retour':
  subprocess.run(['git','fetch','--depth=1','origin',revision],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
  listing=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'assemblage/forgejo'],cwd=ROOT,text=True).splitlines()
  data=io.BytesIO()
  with tarfile.open(fileobj=data,mode='w:gz') as t:
   for path in listing+['scripts/monolithe-sauvegarde.py']:
    if path.endswith(('.nix','.json','.js','.css','.tmpl','.py')):
     content=subprocess.check_output(['git','show',revision+':'+path],cwd=ROOT)
     name='payload/backup-existing.py' if path.startswith('scripts/') else 'payload/'+path.removeprefix('assemblage/forgejo/')
     info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o600
     t.addfile(info,io.BytesIO(content))
  command='umask 077; mkdir -p '+remote+'; tar -xzf - -C '+remote
  subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),command],input=data.getvalue(),check=True)
 command='nix-shell -I nixpkgs='+NIXPKGS+' -p python3 --run '+shlex.quote('python3 -B '+remote+'/payload/promouvoir.py '+phase+' '+revision)
 subprocess.run(['sh',str(ROOT/'scripts/connect.sh'),command],check=True)

if __name__=='__main__':main()
