"""Promotion du seul client Log et binaire métier, sans migration ni invitation.

Opérateur Root transmis par la CI centrale. Native, PG et les services tiers
restent dans leur génération/version ; le retour ne restaure aucune base.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT=Path('/root/mrjam-corrections/log-interface')


def exiger(v,message):
    if not v:raise ValueError(message)


def module(nom,path):
    s=importlib.util.spec_from_file_location(nom,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def ecrire(p,v):
    tmp=p.with_name(p.name+'.nouveau');tmp.write_text(json.dumps(v,indent=2)+'\n');os.replace(tmp,p)


def configuration(cible):
    p=Path('/etc/nixos/configuration.nix');tmp=p.with_name('configuration.nix.mrjam-interface')
    exiger(not tmp.exists() and not tmp.is_symlink(),'Configuration concurrente')
    tmp.symlink_to(cible);os.replace(tmp,p)


def charger_stage(plan):
    rev=plan['revision_assemblage'];exiger(re.fullmatch('[a-f0-9]{40}',rev),'Assemblage invalide')
    return module('stage_interface',Path('/root/mrjam-assemblages')/rev/'payload/vps/scripts/monolithe-preparer.py')


def pids(stage,d):
    return {n:stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip()
            for n in (*stage.TIERS,'kanidm','postgresql','mrjam-metier')}


def retour(d,stage,plan):
    exiger(stage.etat(d)['generation'] in (plan['avant']['generation'],plan['candidat']),'Bascule concurrente')
    configuration(plan['avant']['configuration_lien'] or plan['avant']['configuration_cible'])
    stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',plan['avant']['generation']],d)
    stage.commande([plan['avant']['generation']+'/bin/switch-to-configuration','switch'],d)
    ecrire(d/'retour.json',{'code_seul':True,'donnees_et_identites_non_restaurees':True})


def promouvoir(d):
    exiger(os.geteuid()==0,'Root requis');os.umask(0o077);sys.dont_write_bytecode=True
    plan=json.loads((d/'candidat.json').read_text());stage=charger_stage(plan)
    exiger(not (d/'plan.json').exists(),'Opération déjà engagée : constater son issue')
    avant=stage.etat(d)
    exiger(avant['generation']==plan['generation_attendue']==avant['demarrage'],'Production différente')
    payload=d/'payload';fichiers=plan['fichiers']
    for nom,h in fichiers.items():
        p=(payload/nom).resolve()
        exiger(p.is_relative_to(payload.resolve()) and p.is_file() and not p.is_symlink() and sha(p)==h,'Payload différent')
    with (payload/'image.nar').open('rb') as f:
        rimport=subprocess.run(['nix-store','--import'],stdin=f,capture_output=True,timeout=1800)
    exiger(rimport.returncode==0,'Import NAR refusé')
    image=Path(plan['paquet_metier'])/'bin/mrjam-metier'
    exiger(sha(image)==plan['artefact_sha256'],'Image différente du candidat qualifié')
    site=payload/'site'
    module_interface=payload/'module.nix';evaluation=payload/'evaluation.nix'
    expression='import '+str(evaluation)+' { configuration='+json.dumps(avant['configuration_cible'])+'; moduleInterface='+json.dumps(str(module_interface))+'; site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-log-interface"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }'
    r=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--json','--expr',expression],d))
    exiger(r['avant']==avant['generation'] and r['invariants'] and r['assertions'] and r['nativeActif'],'Configuration hors périmètre')
    exiger(r['paquetApres']==plan['paquet_metier'],'Autre paquet métier')
    cfg=d/'configuration.nix'
    cfg.write_text('{ lib, ... }: let b=(import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ '+json.dumps(avant['configuration_cible'])+' ]; }).config; in { imports = [ '+json.dumps(avant['configuration_cible'])+' (import '+str(module_interface)+' { locations=b.services.nginx.virtualHosts."log.mrj.am".locations; site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-log-interface"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }) ]; }\n')
    gcroot=Path('/nix/var/nix/gcroots/mrjam-log-interface')/d.name;gcroot.parent.mkdir(parents=True,exist_ok=True)
    generation=stage.commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+stage.NIXPKGS,
        '-I','nixos-config='+str(cfg),'--out-link',gcroot,'--max-jobs','1','--cores','2'],d).decode().strip()
    exiger(generation==r['apres'],'Génération différente de l’évaluation')
    exiger(Path(r['exeApres']).read_text()==Path(r['exeAvant']).read_text().replace(r['paquetAvant'],r['paquetApres']),
           'Autre changement du script de démarrage')
    nginx=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+/bin/nginx',r['nginx'])
    configs=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+\.conf',r['nginx'])
    exiger(len(nginx)==len(configs)==1,'Configuration Nginx ambiguë')
    stage.commande([nginx[0],'-t','-c',configs[0]],d)
    processus=pids(stage,d)
    exiger(sha(Path('/proc')/processus['mrjam-metier']/'exe')==plan['artefact_avant'],'Code actif différent')
    # Restauration actuelle isolée avec le mécanisme central déjà qualifié.
    # Aucun schéma/format ne change ; le retour garde les données courantes.
    backup=module('backup_interface',Path('/root/mrjam-assemblages')/plan['revision_assemblage']/'payload/vps/scripts/monolithe-sauvegarde.py')
    backup.GENERATION=avant['generation'];backup.main(d.name)
    stage.commande(['systemctl','start','mrjam-sauvegarde.service'],d)
    resultat=stage.commande(['systemctl','show','mrjam-sauvegarde.service','-p','Result','--value'],d).decode().strip()
    exiger(resultat=='success','Sauvegarde actuelle refusée')
    exiger(stage.etat(d)==avant,'Bascule concurrente')
    etat=dict(plan,avant=avant,candidat=generation,pids=processus)
    ecrire(d/'plan.json',etat)
    timer='mrjam-log-interface-retour-'+d.name[:12]
    stage.commande(['systemd-run','--unit='+timer,'--on-active=5min',
        '/run/current-system/sw/bin/nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3','--run',
        'python3 -B '+str(payload/'promouvoir.py')+' retour '+d.name],d)
    try:
        stage.commande(['systemctl','stop','mrjam-metier'],d)
        postgres=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--json','--expr',
            '(import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ '+json.dumps(avant['configuration_cible'])+' ]; }).config.services.postgresql.finalPackage.outPath'],d))
        def donnees():
            return {b:backup.schema(lambda q,b=b:backup.sql(Path(postgres)/'bin',Path('/run/postgresql'),b,q))
                    for b in ('vision','matheval')}
        reference=donnees();ecrire(d/'donnees-avant-privees.json',reference)
        configuration(str(cfg))
        stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',generation],d)
        stage.commande([generation+'/bin/switch-to-configuration','switch'],d)
        stage.commande(['systemctl','start','mrjam-metier'],d)
        exiger(donnees()==reference,'Invariants métier différents')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation,'Activation non constatée')
        maintenant=pids(stage,d)
        exiger(all(maintenant[n]==pid for n,pid in processus.items() if n!='mrjam-metier'),'Service protégé redémarré')
        exiger(sha(Path('/proc')/maintenant['mrjam-metier']/'exe')==plan['artefact_sha256'],'Binaire servi différent')
        stage.commande(['systemctl','is-active','mrjam-metier','kanidm','nginx','postgresql'],d)
        for rel,h in plan['site_fichiers'].items():
            url='https://log.mrj.am/'+('ui/login' if rel=='index.html' else rel)
            with urllib.request.urlopen(url,timeout=20) as response:
                exiger(response.status==200 and hashlib.sha256(response.read(4*1024*1024+1)).hexdigest()==h,'Ressource servie différente')
        stage.commande(['systemctl','stop',timer+'.timer'],d)
        preuve={'format':1,'revision_sources':plan['revision_sources'],'generation':generation,
            'artefact_sha256':plan['artefact_sha256'],'site_sha256':plan['site_sha256'],
            'elm_ui_et_animator_servis':True,'tiers_et_kanidm_preserves':True,'schema_et_comptes_non_modifies':True,
            'sauvegarde_actuelle_reussie':True,'restauration_actuelle_isolee_reussie':True,
            'invariants_metier_identiques':True,'retour_code_disponible':True}
        ecrire(d/'termine.json',preuve);print(json.dumps(preuve))
    except Exception:
        retour(d,stage,etat);stage.commande(['systemctl','stop',timer+'.timer'],d);raise


if __name__=='__main__':
    import fcntl
    with open('/root/mrjam-log.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        exiger(len(sys.argv)==3 and sys.argv[1] in ('promouvoir','retour') and re.fullmatch('[a-f0-9]{40}',sys.argv[2]),'Commande refusée')
        d=ROOT/sys.argv[2]
        if sys.argv[1]=='promouvoir':promouvoir(d)
        elif not (d/'termine.json').exists():
            plan=json.loads((d/'plan.json').read_text());retour(d,charger_stage(plan),plan)
