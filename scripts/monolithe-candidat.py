"""Sceller localement l'assemblage qualifié, sans connexion au VPS.

Sources exactes, reçus, ressources et NAR du même binaire ; seul le chiffré age
est publiable. Aucun reçu local n'est converti en attestation CI.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from assemblage import (RACINE, manifeste, chemins_sources, verifier_sources,
                       catalogue, identifiant_suite, compilation_entrees)
from frontends import contenus, cache_style


def exiger(v,message):
    if not v:raise ValueError(message)


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def qualification(executable):
    rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RACINE,text=True).strip()
    exiger(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=RACINE),
           'Commiter les sources avant de sceller le candidat')
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'));m=manifeste()
    verifier_sources(sources,m,exact=True)
    recus={}
    for nom,suite in catalogue().items():
        p=RACINE/'state/recus'/(nom+'.json');r=json.loads(p.read_text())
        exiger(r['resultat']=='succes' and r['confiance']=='locale-non-attestee'
               and r['autorise_publication'] is False
               and r['identite']==identifiant_suite(nom,suite,sources),
               'Qualification absente ou invalidée : '+nom)
        recus[nom]=sha(p)
    q=json.loads(executable.with_suffix('.qualification.json').read_text())
    exiger(q['sources_lisp_sha256']==compilation_entrees(sources),'Graphe Lisp différent')
    exiger(q['artefact_sha256']==sha(executable),'Image locale modifiée')
    exiger(q['compilation']['sbcl']=='2.6.4','Compilateur cible requis')
    exiger(sha(Path(q['sorties_nix']['metier'])/'bin/mrjam-metier')==q['artefact_sha256'],
           'Image différente de la closure Nix')
    return rev,sources,m,recus,q


def sceller(executable,destination):
    rev,sources,m,recus,q=qualification(executable)
    exiger(not destination.exists(),'Candidat existant : aucun remplacement implicite')
    destination.mkdir(mode=0o700,parents=True)
    with tempfile.TemporaryDirectory(prefix='mrjam-candidat-',dir=destination) as tmp:
        tmp=Path(tmp);root=tmp/'payload';root.mkdir(mode=0o700)
        for nom in sources:
            data=subprocess.check_output(['git','archive','HEAD'],cwd=sources[nom])
            cible=root/nom;cible.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                exiger(all(a.isdir() or a.isfile() for a in t.getmembers()),'Lien dans les sources')
                t.extractall(cible,filter='data')
        # Les reçus des consommateurs portent sur leur Style réellement
        # verrouillé, qui peut différer de sa tête actuelle. Sources immuables
        # de qualification dans le bundle privé, sans copie entretenue en dépôt.
        styles={}
        for nom in sorted({s['style_consomme_par'] for s in catalogue().values() if s.get('style_consomme_par')}):
            edge=m['frontends'][nom]
            cache=cache_style(sources['style'],edge['revision_style'])
            cible=root/'styles-consommes'/nom
            shutil.copytree(cache,cible)
            (cible/'.provenance-centrale.json').unlink(missing_ok=True)
            styles[nom]={'revision':edge['revision_style'],'fichiers':contenus(cible)}
        reference=root/'reference-mcp';reference.mkdir()
        for nom in ('qualification.json','qualification-trace-synthetique.json'):
            shutil.copy2(RACINE/'state/outils-mcp'/nom,reference/nom)
        fronts={}
        for nom in ('vision','matheval','logique','style'):
            r=json.loads((RACINE/'state/frontends-candidats'/('dernier-'+nom+'.json')).read_text())
            p=RACINE/r['candidat']
            exiger(p.resolve().is_relative_to(RACINE/'state/frontends-candidats')
                   and not p.is_symlink() and contenus(p)==r['fichiers'],'Frontend différent')
            shutil.copytree(p,root/'frontends'/nom)
            fronts[nom]={k:r[k] for k in ('revision','fichiers','ensemble_sha256')}
        shutil.copytree(RACINE/'state/recus',root/'recus')
        (root/'qualification.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
        fermeture=sorted(set(subprocess.check_output(['nix-store','-qR',*q['sorties_nix'].values()],text=True).splitlines()))
        exiger(all(re.fullmatch(r'/nix/store/[a-z0-9]{32}-[^/\s]+',p) for p in fermeture),'Closure invalide')
        # Les sorties propres sont promues, jamais reconstruites. Les autres
        # chemins sont les paquets officiels déjà qualifiés : substitution Nix
        # avec signatures du cache existant, pas 568 Mo de doublons transportés.
        sorties=sorted(q['sorties_nix'].values())
        cache=[p for p in fermeture if p not in sorties]
        with (root/'closure.nar').open('xb') as f:subprocess.run(['nix-store','--export',*sorties],stdout=f,check=True)
        exiger((root/'closure.nar').stat().st_size<1024**3,'Closure hors limite')
        cert={'format':2,'revision':rev,'revision_construction':q['source_revision'],
              'origine_preuves':'codex-local-non-attestee','manifest':m,
              'recus_locaux_sha256':recus,'qualification':q,'frontends':fronts,'styles_consommes':styles,
              'closure':fermeture,'closure_cache':cache,'fichiers':contenus(root),'activation':False}
        (root/'stage.json').write_text(json.dumps(cert,ensure_ascii=False,indent=2)+'\n')
        archive=tmp/'candidat.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=1) as t:t.add(root,arcname='payload',recursive=True)
        exiger(archive.stat().st_size<1024**3,'Archive hors limite')
        connu=(RACINE/'scripts/ssh-known-hosts').read_text().strip().split()
        exiger(len(connu)==3 and connu[0]=='187.77.95.158' and connu[1]=='ssh-ed25519','Clé hôte inattendue')
        recipient=' '.join(connu[1:]);cipher=destination/'candidat.tar.gz.age'
        subprocess.run([Path(q['sorties_nix']['outils'])/'age/bin/age','-r',recipient,'-o',cipher,archive],check=True)
        preuve={'format':1,'revision_operateurs':rev,'revision_construction':q['source_revision'],
                'artefact_sha256':q['artefact_sha256'],'cipher_sha256':sha(cipher),
                'archive_sha256':sha(archive),'stage_sha256':sha(root/'stage.json'),
                'cipher_octets':cipher.stat().st_size,'recipient_ssh':recipient,
                'origine_preuves':'codex-local-non-attestee','soumission_autorisee_par_proprietaire':False}
        (destination/'soumission.json').write_text(json.dumps(preuve,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'revision':rev,'cipher_sha256':preuve['cipher_sha256'],
                      'octets':preuve['cipher_octets'],'publication':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();sceller(a.executable.resolve(),a.destination.resolve())
