"""Préparer un système Nix depuis le candidat CI reçu, sans activation.

Le bundle est privé. Erreurs détaillées restent sur le VPS ; seuls agrégats et
révisions sont imprimés. Aucune migration SQL, tâche métier, IdP ou SMTP ici.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import traceback

NIXPKGS='/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
TIERS=('sshd','mrj-auth','keycloak','vision-embeddings','phpfpm-nextcloud',
       'redis-nextcloud','nextcloud-backup.timer','postgresqlBackup-vision.timer',
       'postgresqlBackup-matheval.timer')
ETATS={
 'cycle-courriels':'/var/lib/vision-cycle/courriels.sqlite',
 'admissions':'/var/lib/mrjam-admission/admissions.sqlite',
 'admission-courriels':'/var/lib/mrjam-admission/courriels.sqlite',
 'fermeture-courriels':'/var/lib/mrjam-fermeture/courriels.sqlite',
 'courriel':'/var/lib/mrjam-courriel/file.sqlite',
 'effacements':'/var/lib/vision-effacements/demandes.jsonl',
 'effacements-cycle':'/var/lib/vision-cycle/effacements.jsonl',
 'effacements-fermeture':'/var/lib/mrjam-fermeture/effacements.jsonl'}


def exiger(v,message):
    if not v:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def commande(args,d,*,input=None,timeout=1800):
    p=subprocess.run([str(a) for a in args],input=input,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode:
        (d/'erreur-commande-privee.log').write_bytes(p.stderr)
        raise RuntimeError('Commande refusée ; journal privé sur le VPS')
    return p.stdout


def verifier_bundle(root):
    cert=json.loads((root/'stage.json').read_text())
    exiger(cert['format']==1 and cert['activation'] is False,'Format de stage refusé')
    files={}
    for p in root.rglob('*'):
        s=p.lstat();exiger(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'Fichier non régulier dans le bundle')
        if p.is_file() and p!=root/'stage.json':files[str(p.relative_to(root))]=sha(p)
    exiger(files==cert['fichiers'],'Empreintes de bundle différentes')
    exiger(cert['manifest']['toolchain']['production']['nixpkgs']==NIXPKGS,'Toolchain différente')
    q=cert['qualification'];paquet=Path(q['sorties_nix']['metier'])
    exiger(re.fullmatch(r'/nix/store/[a-z0-9]{32}-mrjam-metier-[a-f0-9]{12}',str(paquet)), 'Paquet Nix non reconnu')
    exiger(sha(paquet/'bin/mrjam-metier')==q['artefact_sha256'],'Binaire différent de la qualification')
    exiger(q['source_revision']==cert['revision'],'Révision incohérente')
    return cert


def etat(d):
    entree=Path('/etc/nixos/configuration.nix')
    return {'generation':str(Path('/run/current-system').resolve()),
      'demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
      'configuration_sha256':sha(entree),'configuration_cible':str(entree.resolve()),
      'configuration_lien':os.readlink(entree) if entree.is_symlink() else None,
      'publications':{n:str(Path('/srv')/n/'current') for n in ('vision','vision-interface','matheval','logique')},
      'cibles':{n:str((Path('/srv')/n/'current').resolve()) for n in ('vision','vision-interface','matheval','logique')},
      'tiers_pids':{n:commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip() for n in TIERS}}


def inventaire_etats():
    result={}
    for n,path in ETATS.items():
        p=Path(path)
        if not p.exists():result[n]={'present':False};continue
        s=p.lstat();exiger(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'État durable non régulier')
        result[n]={'present':True,'mode':oct(stat.S_IMODE(s.st_mode)),
                   'uid':s.st_uid,'gid':s.st_gid,'octets':s.st_size}
    return result


def preparer(revision):
    exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision),'Opérateur/révision refusés')
    os.umask(0o077)
    d=Path('/root/mrjam-assemblages')/revision
    exiger(d.is_dir() and not d.is_symlink() and stat.S_IMODE(d.stat().st_mode)==0o700,'Stage non privé')
    root=d/'payload';cert=verifier_bundle(root)
    exiger(cert['revision']==revision,'Bundle d’une autre révision')
    exiger(not (d/'preparation.json').exists(),'Préparation déjà réalisée')
    avant=etat(d)
    exiger(avant['generation']==avant['demarrage'],'Bascule concurrente')
    exiger(commande(['nix-instantiate','--find-file','nixpkgs'],d).decode().strip()==NIXPKGS,'Nixpkgs installé différent')
    commande(['systemctl','is-active',*TIERS,'nginx','postgresql','vision','matheval'],d)
    exiger(shutil.disk_usage('/').free>10*1024**3,'Espace insuffisant')
    # Aucun secret lu. Le corpus et la version sont issus de la source qualifiée.
    bank=json.loads((root/'matheval/research/bank.json').read_text())
    version=bank['version'];exiger(re.fullmatch('[A-Za-z0-9._-]+',version),'Version corpus invalide')
    public=Path('/srv/mrjam-assemblages')/revision
    exiger(not public.exists(),'Ressources déjà préparées ; vérifier la reprise')
    public.parent.mkdir(mode=0o755,exist_ok=True)
    public.mkdir(mode=0o755)
    for nom in cert['frontends']:
        shutil.copytree(root/'frontends'/nom,public/nom)
    for p in (public,*public.rglob('*')):
        exiger(not p.is_symlink(),'Lien dans les ressources')
        p.chmod(0o755 if p.is_dir() else 0o644)
    params={'configuration':avant['configuration_cible'],
            'paquet':cert['qualification']['sorties_nix']['metier'],
            'documentVision':str(public/'vision'),
            'ressourcesMatheval':str(public/'matheval'),
            'bankVersion':version}
    args=['nix-instantiate','-I','nixpkgs='+NIXPKGS,'--eval','--strict','--json',root/'vps/scripts/monolithe-config.nix']
    for k,v in params.items():args.extend(['--argstr',k,v])
    r=json.loads(commande(args,d))
    (d/'evaluation-privee.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    exiger(r['avant']==avant['generation'],'Les sources actives ne reproduisent pas le système')
    exiger(r['assertions'] and r['invariantAvant']==r['invariantApres'],'Un service préservé changerait')
    expression='(import '+str(root/'vps/scripts/monolithe-evaluation.nix')+' { '+''.join(k+'='+json.dumps(v)+'; ' for k,v in params.items())+'}).moduleCandidate'
    candidate=d/'configuration-candidate.nix'
    candidate.write_text('{ imports = [ '+json.dumps(avant['configuration_cible'])+' '+expression+' ]; }\n')
    racines=Path('/nix/var/nix/gcroots/mrjam-metier')/revision;racines.mkdir(parents=True,exist_ok=False)
    for n,p in {'avant':avant['generation'],'nixpkgs':NIXPKGS,'image':params['paquet'],
                'outils':cert['qualification']['sorties_nix']['outils']}.items():(racines/n).symlink_to(p)
    construit=commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+NIXPKGS,
        '-I','nixos-config='+str(candidate),'--out-link',racines/'candidat','--max-jobs','1','--cores','2'],d).decode().strip()
    exiger(construit==r['apres'],'Construction différente de l’évaluation')
    commande(shlex.split(r['nginx'])+['-t'],d)
    simulation=commande([Path(construit)/'bin/switch-to-configuration','dry-activate'],d).decode()
    (d/'simulation-privee.txt').write_text(simulation)
    for ligne in simulation.splitlines():
        if 'stopping the following units:' in ligne or 'restarting the following units:' in ligne:
            exiger(not any(n.replace('.timer','')+'.service' in ligne for n in TIERS), 'Redémarrage tiers imprévu')
    exiger(etat(d)==avant,'État modifié pendant préparation')
    preuve={'format':1,'revision':revision,'run_ci':cert['run'],'avant':avant,'candidat':construit,
            'configuration':str(candidate),'parametres':params,'etats_durables':inventaire_etats(),
            'artefact_sha256':cert['qualification']['artefact_sha256'],
            'systeme_construit':True,'activation':False,'sauvegarde_actuelle_requise':True,
            'restauration_acl_et_retour_restants':True}
    (d/'preparation.json').write_text(json.dumps(preuve,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in preuve.items() if k not in ('avant','parametres','etats_durables')},ensure_ascii=False))


if __name__=='__main__':
    try:
        with open('/root/mrjam-assemblage.lock','a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);preparer(sys.argv[1])
    except Exception:
        if len(sys.argv)==2 and re.fullmatch('[a-f0-9]{40}',sys.argv[1]):
            d=Path('/root/mrjam-assemblages')/sys.argv[1]
            if d.is_dir() and not d.is_symlink():
                (d/'erreur-preparation-privee.log').write_text(traceback.format_exc())
        print('Préparation refusée ; aucun système activé, diagnostic privé sur le VPS.',file=sys.stderr)
        sys.exit(1)
