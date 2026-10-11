"""Recevoir en CI le candidat privé qualifié dans Codex, sans refaire ses tests.

Le descripteur sur main et l'uploader propriétaire définissent la confiance dans
la soumission. Les reçus restent locaux, non attestés. SSH existant uniquement.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from assemblage import RACINE, manifeste


def exiger(v,message):
    if not v:raise ValueError(message)


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def descriptor():
    d=json.loads((RACINE/'operations/monolithe-candidat.json').read_text())
    exiger(d['format']==1 and d['soumission_autorisee_par_proprietaire'] is True,'Soumission non scellée')
    exiger(d['origine_preuves']=='codex-local-non-attestee','Origine inconnue')
    for k in ('revision_operateurs','revision_construction'):exiger(re.fullmatch('[a-f0-9]{40}',d[k]),'Révision invalide')
    for k in ('cipher_sha256','archive_sha256','stage_sha256','artefact_sha256'):exiger(re.fullmatch('[a-f0-9]{64}',d[k]),'Empreinte invalide')
    exiger(0<d['cipher_octets']<1024**3,'Candidat hors limite')
    connu=(RACINE/'scripts/ssh-known-hosts').read_text().strip().split()
    exiger(d['recipient_ssh']==' '.join(connu[1:]),'Destinataire différent de la clé hôte')
    exiger(d['depot']=='MrJ-am/vps-infrastructure','Dépôt inconnu')
    if d.get('transport')=='git-chiffre':
        exiger(re.fullmatch('[a-f0-9]{40}',d['revision_transport']) and
               d['chemin_transport']=='candidat.tar.gz.age','Transport Git non verrouillé')
    else:
        exiger(d['uploader_id']==12571490,'Producteur inconnu')
        exiger(isinstance(d['asset_id'],int) and d['asset_id']>0,'Asset invalide')
    return d


def ssh(commande,**kwargs):
    return subprocess.run(['sh',str(RACINE/'scripts/connect.sh'),commande],check=True,**kwargs)


def main():
    exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REF')=='refs/heads/main',
           'Promotion réservée au déploiement central sur main')
    exiger(os.environ.get('GITHUB_REPOSITORY')=='MrJ-am/vps-infrastructure','Dépôt inconnu')
    d=descriptor();rev=d['revision_operateurs'];remote='/root/mrjam-assemblages/'+rev
    with tempfile.TemporaryDirectory(prefix='mrjam-promotion-') as tmp:
        cipher=Path(tmp)/'candidat.age'
        if d.get('transport')=='git-chiffre':
            depot=Path(tmp)/'git'
            subprocess.run(['git','init','--bare','--quiet',depot],check=True)
            subprocess.run(['git','--git-dir='+str(depot),'fetch','--quiet','--no-tags','--depth=1',
                'https://github.com/MrJ-am/vps-infrastructure.git',d['revision_transport']],check=True)
            with cipher.open('xb') as f:subprocess.run(['git','--git-dir='+str(depot),'show',
                d['revision_transport']+':'+d['chemin_transport']],stdout=f,check=True)
        else:
            endpoint='repos/MrJ-am/vps-infrastructure/releases/assets/'+str(d['asset_id'])
            meta=json.loads(subprocess.check_output(['gh','api',endpoint]))
            exiger(meta['uploader']['id']==d['uploader_id'] and meta['size']==d['cipher_octets']
                   and meta['name']=='candidat.tar.gz.age','Asset différent de la soumission')
            with cipher.open('xb') as f:subprocess.run(['gh','api',endpoint,'-H','Accept: application/octet-stream'],stdout=f,check=True)
        exiger(cipher.stat().st_size==d['cipher_octets'] and sha(cipher)==d['cipher_sha256'],'Chiffré modifié')
        ssh('set -eu; umask 077; install -d -m 700 /root/mrjam-assemblages; '+
            'if test -e '+remote+'; then test -d '+remote+'; test ! -L '+remote+
            '; else mkdir -m 700 '+remote+'; fi; cat > '+remote+'/candidat.age-reception; '+
            'mv '+remote+'/candidat.age-reception '+remote+'/candidat.age',stdin=cipher.open('rb'))
        bootstrap="""import hashlib,json,pathlib,subprocess,sys,tarfile
d=json.loads(sys.argv[2]);p=pathlib.Path(sys.argv[1]);c=p/'candidat.age';a=p/'candidat.tar.gz'
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as r:
  for b in iter(lambda:r.read(1048576),b''):h.update(b)
 return h.hexdigest()
assert sha(c)==d['cipher_sha256']
assert ' '.join(subprocess.check_output(['ssh-keygen','-y','-f','/etc/ssh/ssh_host_ed25519_key'],text=True).split()[:2])==d['recipient_ssh']
if not (p/'payload').exists():
 subprocess.run(['age','-d','-i','/etc/ssh/ssh_host_ed25519_key','-o',str(a),str(c)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 assert sha(a)==d['archive_sha256']
 with tarfile.open(a) as t:
  ms=t.getmembers()
  assert len(ms)<50000 and sum(m.size for m in ms)<2147483648
  assert all((m.isdir() or m.isfile()) and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts and m.name.split('/')[0]=='payload' for m in ms)
  assert len({m.name for m in ms})==len(ms)
  t.extractall(p,filter='data')
assert sha(p/'payload/stage.json')==d['stage_sha256']
s=json.loads((p/'payload/stage.json').read_text())
assert s['format']==2 and s['revision']==d['revision_operateurs'] and s['revision_construction']==d['revision_construction']
assert s['qualification']['artefact_sha256']==d['artefact_sha256']
for name,h in s['fichiers'].items():
 f=p/'payload'/name
 assert f.resolve().is_relative_to(p/'payload') and not f.is_symlink() and sha(f)==h
if 'closure_cache' in s:
 import re
 assert all(re.fullmatch('/nix/store/[a-z0-9]{32}-[^/\\\\s]+',x) for x in s['closure'])
 assert set(s['closure_cache'])==set(s['closure'])-set(s['qualification']['sorties_nix'].values())
 subprocess.run(['nix-store','--realise',*s['closure_cache']],stdout=subprocess.DEVNULL,check=True)
with (p/'payload/closure.nar').open('rb') as f:subprocess.run(['nix-store','--import'],stdin=f,stdout=subprocess.DEVNULL,check=True)
(p/'soumission.json').write_text(json.dumps(d,indent=2)+'\\n')
(p/'promotion.json').write_text(json.dumps({'format':1,'run_ci':int(sys.argv[3]),'revision_deploiement':sys.argv[4],'origine':'soumission-locale-proprietaire-verifiee'},indent=2)+'\\n')
a.unlink(missing_ok=True)
subprocess.run([sys.executable,'-B',str(p/'payload/vps/scripts/monolithe-preparer.py'),p.name],check=True)
"""
        cmd='python3 -c '+shlex.quote(bootstrap)+' '+remote+' '+shlex.quote(json.dumps(d))+' '+os.environ['GITHUB_RUN_ID']+' '+os.environ['GITHUB_SHA']
        shell='nix-shell -I nixpkgs='+manifeste()['toolchain']['production']['nixpkgs']+' -p python3 age --run '+shlex.quote(cmd)
        ssh(shell)


if __name__=='__main__':main()
