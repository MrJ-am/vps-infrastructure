"""Transport du client Log qualifié par le seul canal CI administratif existant."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from assemblage import RACINE, catalogue, entrees


def exiger(v,message):
    if not v:raise ValueError(message)


def main():
    exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main','CI main requise')
    p=json.loads((RACINE/'operations/log-interface-candidat.json').read_text())
    exiger(p['format']==1 and p['origine_preuves']=='codex-local-non-attestee','Provenance absente')
    exiger(set(p['recus'])=={'log-protocole-elm','log-interface','log-interface-promotion','log-parcours'},'Qualification incomplète')
    exiger(re.fullmatch('[a-f0-9]{40}',p['revision_sources']) and re.fullmatch('[a-f0-9]{40}',p['revision_transport']),'Révisions invalides')
    for nom,h in p['sources_qualifiees'].items():
        f=RACINE/nom
        exiger(f.resolve().is_relative_to(RACINE) and hashlib.sha256(f.read_bytes()).hexdigest()==h,'Source non qualifiée')
        exiger(subprocess.check_output(['git','show',p['revision_sources']+':'+nom],cwd=RACINE)==f.read_bytes(),'Source différente du commit qualifié')
    suites=catalogue()
    for nom,r in p['recus'].items():
        exiger(r['resultat']=='succes' and r['confiance']=='locale-non-attestee' and r['autorise_publication'] is False,
               'Contrôle local refusé')
        exiger(len(r['codes'])==len(suites[nom]['commandes']) and all(c==0 for c in r['codes']),'Commandes non exécutées')
        exiger(r['identite']['definition']==hashlib.sha256(json.dumps(suites[nom],sort_keys=True).encode()).hexdigest(),'Suite différente')
        # Les producteurs composants sont verrouillés dans le manifeste et les
        # preuves de construction ; checkout CI limité à l'assembleur.
        local=dict(suites[nom]);local['entrees']={'vps':suites[nom]['entrees'].get('vps',[])}
        exiger(entrees(local,{'vps':RACINE})=={k:v for k,v in r['identite']['entrees'].items() if k.startswith('vps/')},'Entrées locales différentes')
    connu=(RACINE/'scripts/ssh-known-hosts').read_text().strip().split()
    exiger(p['recipient_ssh']==' '.join(connu[1:]),'Destinataire différent')
    s=importlib.util.spec_from_file_location('stage_interface',RACINE/'scripts/monolithe-stage.py')
    stage=importlib.util.module_from_spec(s);s.loader.exec_module(stage)
    with tempfile.TemporaryDirectory(prefix='mrjam-interface-ci-') as temp:
        temp=Path(temp);repo=temp/'transport';repo.mkdir()
        subprocess.run(['git','init','--quiet'],cwd=repo,check=True)
        subprocess.run(['git','fetch','--quiet','--depth','1','https://github.com/MrJ-am/vps-infrastructure.git',p['revision_transport']],cwd=repo,check=True)
        cipher=temp/'candidat.age'
        with cipher.open('wb') as f:
            for nom in p['parties_transport']:
                exiger(re.fullmatch('candidat.tar.gz.age.part-[0-9]{3}',nom),'Partie invalide')
                subprocess.run(['git','show',p['revision_transport']+':'+nom],cwd=repo,stdout=f,check=True)
        exiger(cipher.stat().st_size==p['cipher_octets'] and hashlib.sha256(cipher.read_bytes()).hexdigest()==p['cipher_sha256'],'Chiffré différent')
        remote='/root/mrjam-corrections/log-interface/'+p['revision_sources']
        cmd='set -eu; umask 077; install -d -m 700 '+shlex.quote(remote)+'; test ! -e '+shlex.quote(remote+'/plan.json')+'; cat > '+shlex.quote(remote+'/candidat.age')
        with cipher.open('rb') as f:stage.ssh(cmd,stdin=f)
        bootstrap='''import hashlib,json,pathlib,subprocess,tarfile,os,sys
os.umask(0o077)
plan=json.loads(sys.argv[2]);d=pathlib.Path(sys.argv[1]);c=d/'candidat.age';a=d/'candidat.tar.gz'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
assert sha(c)==plan['cipher_sha256']
assert ' '.join(subprocess.check_output(['ssh-keygen','-y','-f','/etc/ssh/ssh_host_ed25519_key'],text=True).split()[:2])==plan['recipient_ssh']
subprocess.run(['age','-d','-i','/etc/ssh/ssh_host_ed25519_key','-o',str(a),str(c)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
assert sha(a)==plan['archive_sha256']
with tarfile.open(a) as t:
 ms=t.getmembers()
 assert len(ms)<100 and sum(m.size for m in ms)<536870912
 assert all(m.isfile() and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts and m.name.startswith('payload/') for m in ms)
 assert len({m.name for m in ms})==len(ms)
 t.extractall(d,filter='data')
a.unlink()
for nom,h in plan['fichiers'].items(): assert sha(d/'payload'/nom)==h
(d/'candidat.json').write_text(json.dumps(plan)+'\\n')
subprocess.run([sys.executable,'-B',str(d/'payload/promouvoir.py'),'promouvoir',d.name],check=True)
'''
        cmd='python3 -c '+shlex.quote(bootstrap)+' '+shlex.quote(remote)+' '+shlex.quote(json.dumps(p))
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 age --run '+shlex.quote(cmd))


if __name__=='__main__':main()
