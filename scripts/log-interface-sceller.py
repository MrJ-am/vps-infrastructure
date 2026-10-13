"""Sceller le binaire et le site qualifiés, en flux chiffré, sans doublons NAR."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

from assemblage import RACINE, catalogue, chemins_sources, identifiant_suite, compilation_entrees
from frontends import contenus


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def main(destination):
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=RACINE):
        raise ValueError('Sources infrastructure non commitées')
    rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RACINE,text=True).strip()
    sources=chemins_sources();recus={};suites=catalogue()
    for nom in ('log-protocole-elm','log-interface','log-interface-promotion','log-parcours'):
        r=json.loads((RACINE/'state/recus'/f'{nom}.json').read_text())
        if r['resultat']!='succes' or r['identite']!=identifiant_suite(nom,suites[nom],sources):
            raise ValueError('Qualification différente : '+nom)
        recus[nom]=r
    construction=json.loads((RACINE/'state/artefacts/mrjam-metier.construction-nix.json').read_text())
    paquet=construction['sorties_nix']['metier'];image=Path(paquet)/'bin/mrjam-metier'
    if construction['sources_lisp_sha256']!=compilation_entrees(sources):
        raise ValueError('Binaire différent des sources qualifiées')
    qualification=json.loads((RACINE/'state/artefacts/mrjam-metier.qualification.json').read_text())
    if qualification['artefact_sha256']!=sha(image) or qualification['sources_lisp_sha256']!=construction['sources_lisp_sha256']:
        raise ValueError('Binaire non qualifié ou sources différentes')
    site=RACINE/'interface-log/dist';rapport=json.loads((RACINE/'state/log-interface-construction.json').read_text())
    if contenus(site)!=rapport['fichiers']:raise ValueError('Site changé après construction')
    fichiers={};entrees={};mapping={'promouvoir.py':'scripts/log-interface-promouvoir.py',
        'module.nix':'assemblage/log-interface/module.nix','evaluation.nix':'assemblage/log-interface/evaluation.nix'}
    for nom,path in mapping.items():
        fichiers[nom]=sha(RACINE/path);entrees[nom]=RACINE/path
    for nom,h in rapport['fichiers'].items():fichiers['site/'+nom]=h;entrees['site/'+nom]=site/nom
    # Mesure du flux export officiel, sans fichier NAR temporaire.
    def exporter():return subprocess.Popen(['nix-store','--export',paquet],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    proc=exporter();taille=0;h=hashlib.sha256()
    for b in iter(lambda:proc.stdout.read(1048576),b''):taille+=len(b);h.update(b)
    if proc.wait()!=0:raise ValueError('Export NAR refusé')
    fichiers['image.nar']=h.hexdigest()
    destination.mkdir(parents=True,exist_ok=True);cipher=destination/'candidat.tar.gz.age'
    if cipher.exists():raise ValueError('Candidat déjà scellé')
    recipient=' '.join((RACINE/'scripts/ssh-known-hosts').read_text().strip().split()[1:])
    age=subprocess.Popen(['age','-r',recipient,'-o',str(cipher)],stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
    archive_hash=hashlib.sha256()
    class Conduit:
        def write(self,b):archive_hash.update(b);return age.stdin.write(b)
        def flush(self):age.stdin.flush()
    with tarfile.open(fileobj=Conduit(),mode='w|gz',compresslevel=1) as t:
        for nom,p in entrees.items():t.add(p,arcname='payload/'+nom,recursive=False)
        info=tarfile.TarInfo('payload/image.nar');info.size=taille;info.mode=0o600
        proc=exporter();t.addfile(info,proc.stdout)
        if proc.wait()!=0:raise ValueError('Export final NAR refusé')
    age.stdin.close()
    if age.wait()!=0:raise ValueError('Chiffrement refusé')
    tracked=subprocess.check_output(['git','ls-files','interface-log','lisp/serveur','mrjam-metier.asd',
        'scripts/log-interface-*.py','scripts/log-operation.py','.github/workflows/log-deploiement.yml',
        'assemblage/log-interface','assemblage/manifest.json','assemblage/suites.json',
        'scripts/revoir-frontends.py','assemblage/elm-review/ressources.json'],cwd=RACINE,text=True).splitlines()
    p=dict(format=1,revision_sources=rev,revision_construction=construction['source_revision'],qualification_image=qualification,
        revision_assemblage='54988ca67567db04d2e064feae91d558f7bb25fb',
        generation_attendue='/nix/store/61lianh06k1x18jaikq6azyapn059q7x-nixos-system-nixos-26.05.8639.c5c4a43b0e80',
        artefact_avant='bc70c8225908dd0c566fdcb27a49d62e8b1e39d46c81862098a5221676e9fcbb',
        paquet_metier=paquet,artefact_sha256=sha(image),site_fichiers=rapport['fichiers'],site_sha256=rapport['ensemble_sha256'],
        fichiers=fichiers,recipient_ssh=recipient,archive_sha256=archive_hash.hexdigest(),cipher_sha256=sha(cipher),
        cipher_octets=cipher.stat().st_size,origine_preuves='codex-local-non-attestee',recus=recus,
        sources_qualifiees={nom:sha(RACINE/nom) for nom in tracked})
    (destination/'candidat.json').write_text(json.dumps(p,indent=2)+'\n')
    print(json.dumps({'revision_sources':rev,'cipher_octets':p['cipher_octets'],'publication':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args();main(a.destination)
