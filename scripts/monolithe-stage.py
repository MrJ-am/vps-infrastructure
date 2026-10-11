"""Transférer le candidat de ce runner qualifié vers le VPS, sans activation.

Pas d'artefact privé dans un dépôt public ou un upload-artifact. SSH utilise le
mécanisme central existant ; NAR et bundle sont conservés uniquement sur le VPS.
Une campagne partielle ne prépare pas une publication de référence.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile
from assemblage import (RACINE,manifeste,chemins_sources,verifier_sources,catalogue,
                       identifiant_suite,compilation_entrees)
from frontends import contenus


def exiger(v,message):
    if not v:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def qualification():
    "Même runner, mêmes empreintes ; les reçus locaux ne sont pas importés."
    rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RACINE,text=True).strip()
    exiger(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_SHA')==rev,
           'Préparation réservée au runner de cette révision')
    exiger(os.environ.get('GITHUB_REF')=='refs/heads/main','Production réservée à main')
    exiger(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=RACINE),
           'Infrastructure modifiée depuis la qualification')
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    m=manifeste();verifier_sources(sources,m,exact=True)
    recus={}
    for nom,suite in catalogue().items():
        p=RACINE/'state/recus'/(nom+'.json');r=json.loads(p.read_text())
        exiger(r['resultat']=='succes' and r['identite']==identifiant_suite(nom,suite,sources),
               'Campagne de référence incomplète ou différente : '+nom)
        recus[nom]=sha(p)
    p=RACINE/'state/artefacts/mrjam-metier.qualification.json';q=json.loads(p.read_text())
    exiger(q['source_revision']==rev and q['sources_lisp_sha256']==compilation_entrees(sources),
           'Image qualifiée différente des sources')
    exiger(q['artefact_sha256']==sha(RACINE/'state/artefacts/mrjam-metier'), 'Binaire modifié')
    exiger(q['compilation']['sbcl']=='2.6.4','Compilateur de production requis')
    exiger(sha(Path(q['sorties_nix']['metier'])/'bin/mrjam-metier')==q['artefact_sha256'],
           'Store différent du candidat testé')
    return rev,sources,m,recus,q


def bundle(rev,sources,m,recus,q,destination):
    with tempfile.TemporaryDirectory(prefix='mrjam-stage-') as tmp:
        tmp=Path(tmp);root=tmp/'payload';root.mkdir(mode=0o700)
        # Git archive exclut credentials, state, caches et modifications privées.
        for nom in ('vps','vision','matheval'):
            data=subprocess.check_output(['git','archive','HEAD'],cwd=sources[nom])
            cible=root/nom;cible.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                exiger(all(a.isdir() or a.isfile() for a in t.getmembers()),'Source avec lien refusée')
                t.extractall(cible,filter='data')
        fronts={}
        for nom in ('vision','matheval','logique','style'):
            r=json.loads((RACINE/'state/frontends-candidats'/('dernier-'+nom+'.json')).read_text())
            p=RACINE/r['candidat']
            exiger(p.resolve().is_relative_to(RACINE/'state/frontends-candidats') and not p.is_symlink(),
                   'Candidat frontend extérieur')
            exiger(contenus(p)==r['fichiers'],'Frontend changé depuis qualification')
            import shutil
            shutil.copytree(p,root/'frontends'/nom)
            fronts[nom]={k:r[k] for k in ('revision','fichiers','ensemble_sha256')}
        (root/'qualification.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
        files=contenus(root)
        cert={'format':1,'revision':rev,'run':int(os.environ['GITHUB_RUN_ID']),
              'manifest':m,'recus_ci_sha256':recus,'qualification':q,'frontends':fronts,
              'fichiers':files,'activation':False}
        (root/'stage.json').write_text(json.dumps(cert,ensure_ascii=False,indent=2)+'\n')
        with tarfile.open(destination,'w') as t:t.add(root,arcname='payload',recursive=True)
    return cert


def ssh(commande,**kwargs):
    return subprocess.run(['sh',str(RACINE/'scripts/connect.sh'),commande],check=True,**kwargs)


def main():
    rev,sources,m,recus,q=qualification()
    remote='/root/mrjam-assemblages/'+rev
    with tempfile.TemporaryDirectory(prefix='mrjam-transfert-') as tmp:
        archive=Path(tmp)/'bundle.tar';cert=bundle(rev,sources,m,recus,q,archive)
        exiger(archive.stat().st_size<=512*1024*1024,'Bundle hors limite')
        # Répertoire nouveau, privé, jamais de remplacement silencieux concurrent.
        ssh('set -eu; umask 077; install -d -m 700 /root/mrjam-assemblages; test ! -e '+remote+
            '; mkdir -m 700 '+remote+'; cat > '+remote+'/bundle.tar',stdin=archive.open('rb'))
        # Export/import de la même closure ; aucune recompilation de l'image.
        fermeture=subprocess.check_output(['nix-store','-qR',q['sorties_nix']['metier'],q['sorties_nix']['outils']],text=True).splitlines()
        exiger(all(re.fullmatch(r'/nix/store/[a-z0-9]{32}-[^/\s]+',p) for p in fermeture),'Closure invalide')
        export=subprocess.Popen(['nix-store','--export',*sorted(set(fermeture))],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            ssh('nix-store --import > '+remote+'/store-import.txt',stdin=export.stdout,stdout=subprocess.DEVNULL)
            export.stdout.close();exiger(export.wait(timeout=120)==0,'Export NAR refusé')
        finally:
            if export.poll() is None:export.terminate();export.wait(timeout=10)
        # Bootstrap à code fixe, hash d'archive lié au bundle produit ici.
        bootstrap="""import hashlib,sys,tarfile,pathlib,subprocess
p=pathlib.Path(sys.argv[1]);a=p/'bundle.tar'
assert hashlib.sha256(a.read_bytes()).hexdigest()==sys.argv[2]
with tarfile.open(a) as t:
 ms=t.getmembers()
 assert len(ms)<50000 and sum(m.size for m in ms)<536870912
 assert all((m.isdir() or m.isfile()) and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts and m.name.split('/')[0]=='payload' for m in ms)
 t.extractall(p,filter='data')
subprocess.run([sys.executable,str(p/'payload/vps/scripts/monolithe-preparer.py'),p.name],check=True)
"""
        commande='python3 -c '+shlex.quote(bootstrap)+' '+shlex.quote(remote)+' '+sha(archive)
        shell='nix-shell -I nixpkgs='+m['toolchain']['production']['nixpkgs']+' -p python3 --run '+shlex.quote(commande)
        ssh(shell)


if __name__=='__main__':main()
