"""Promotion du correctif de reconnexion Vision, sans migration ni invitation.

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
import urllib.error
import sqlite3
import time

ROOT=Path('/root/mrjam-corrections/reconnexion')


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
    return module('stage_reconnexion',ROOT/plan['revision_sources']/'payload/preparer.py')


def pids(stage,d):
    return {n:stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip()
            for n in (*stage.TIERS,'kanidm','postgresql','mrjam-metier')}


def retour(d,stage,plan):
    exiger(stage.etat(d)['generation'] in (plan['avant']['generation'],plan['candidat']),'Bascule concurrente')
    configuration(plan['avant']['configuration_lien'] or plan['avant']['configuration_cible'])
    stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',plan['avant']['generation']],d)
    stage.commande([plan['avant']['generation']+'/bin/switch-to-configuration','switch'],d)
    ecrire(d/'retour.json',{'code_seul':True,'donnees_et_identites_non_restaurees':True})


def registre_clients():
    # Aucun identifiant ni secret imprimé ; l'empreinte reste dans le processus.
    with sqlite3.connect('file:/var/lib/mrjam-metier/log/sessions.sqlite?mode=ro',uri=True) as db:
        return tuple(hashlib.sha256(json.dumps(row).encode()).hexdigest()
                     for row in db.execute('SELECT * FROM log_oauth_clients ORDER BY id'))


def sonder(plan):
    limite=time.monotonic()+30
    while True:
        try:
            with urllib.request.urlopen('https://vision.mrj.am/',timeout=10) as r:
                exiger(r.status==200 and hashlib.sha256(r.read(8*1024*1024)).hexdigest()==plan['site_fichiers']['index.html'],
                       'Interface Vision différente')
            break
        except (urllib.error.URLError,TimeoutError):
            exiger(time.monotonic()<limite,'Vision indisponible');time.sleep(.5)
    for rel,h in plan['site_fichiers'].items():
        if rel not in ('app.js','app.css','manifest.json') and not rel.startswith('assets/mrjam/'):continue
        chemin='interface-manifest.json' if rel=='manifest.json' else rel
        with urllib.request.urlopen('https://vision.mrj.am/'+chemin,timeout=20) as r:
            exiger(r.status==200 and hashlib.sha256(r.read(8*1024*1024)).hexdigest()==h,'Ressource Vision différente')
    try:
        urllib.request.urlopen(urllib.request.Request('https://vision.mrj.am/mcp',data=b'{}',
            headers={'Content-Type':'application/json'}),timeout=20)
        raise ValueError('MCP anonyme accepté')
    except urllib.error.HTTPError as e:
        exiger(e.code==401,'MCP anonyme non refusé')
    with urllib.request.urlopen('https://vision.mrj.am/.well-known/oauth-protected-resource/mcp',timeout=20) as r:
        metadata=json.load(r)
        exiger(r.status==200 and metadata['resource']=='https://vision.mrj.am/mcp',
               'Découverte MCP différente')


def qualifier_retour_independant(d,stage):
    """Précondition réelle du timer : processus temporaire, aucune donnée métier."""
    import time
    marque=d/'retour-independant-temoin'
    if marque.exists():
        exiger(marque.read_text()=='retour-independant','Témoin du retour différent')
        return # Même payload vérifié et même opération, qualifiée en préparation.
    travail='mrjam-reconnexion-temoin-'+d.name[:12]
    timer=travail+'-retour'
    stage.commande(['systemd-run','--unit='+travail,'--property=KillMode=control-group',
        '/run/current-system/sw/bin/sleep','60'],d)
    programme=d/'qualifier-retour.py'
    programme.write_text("import pathlib,subprocess\nsubprocess.run(['systemctl','stop',"+repr(travail+'.service')+"],check=True)\npathlib.Path("+repr(str(marque))+").write_text('retour-independant')\n")
    stage.commande(['systemd-run','--unit='+timer,'--on-active=1s',
        '/run/current-system/sw/bin/nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3',
        '--run','python3 -B '+str(programme)],d)
    try:
        for _ in range(40):
            if marque.exists():break
            time.sleep(.5)
        exiger(marque.exists() and marque.read_text()=='retour-independant','Retour indépendant non exécuté')
        etat=etat_unite(travail+'.service')
        exiger(etat.get('LoadState')=='not-found' or
               (etat.get('ActiveState')=='inactive' and etat.get('MainPID')=='0'),'Processus témoin non arrêté')
    finally:
        for nom in (travail+'.service',timer+'.timer'):
            if etat_unite(nom).get('LoadState')!='not-found':
                stage.commande(['systemctl','stop',nom],d)


def etat_unite(nom):
    """Une unité transitoire arrêtée peut avoir été collectée par systemd."""
    r=subprocess.run(['systemctl','show',nom,'-p','LoadState','-p','ActiveState','-p','MainPID'],
                     capture_output=True,text=True,timeout=15)
    valeurs=dict(l.split('=',1) for l in r.stdout.splitlines() if '=' in l)
    exiger(r.returncode==0 or (r.returncode in (1,4) and valeurs.get('LoadState')=='not-found'),
           'État de l’unité transitoire indisponible')
    return valeurs


def promouvoir(d,activer=True):
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
    expression='import '+str(evaluation)+' { configuration='+json.dumps(avant['configuration_cible'])+'; moduleInterface='+json.dumps(str(module_interface))+'; site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-reconnexion"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }'
    r=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--json','--expr',expression],d))
    ecrire(d/'evaluation-reconnexion.json',r)
    exiger(r['avant']==avant['generation'] and r['invariants'] and r['assertions'] and r['nativeActif'],'Configuration hors périmètre')
    exiger(r['paquetApres']==plan['paquet_metier'],'Autre paquet métier')
    cfg=d/'configuration.nix'
    cfg.write_text('{ ... }: { imports = [ '+json.dumps(avant['configuration_cible'])+' (import '+str(module_interface)+' { site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-reconnexion"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }) ]; }\n')
    gcroot=Path('/nix/var/nix/gcroots/mrjam-reconnexion')/d.name;gcroot.parent.mkdir(parents=True,exist_ok=True)
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
    backup=module('backup_reconnexion',payload/'sauvegarde.py')
    backup.GENERATION=avant['generation'];backup.main(d.name,sqlite_reprise={'log-native':'/var/lib/mrjam-metier/log/sessions.sqlite'})
    stage.commande(['systemctl','start','mrjam-sauvegarde.service'],d)
    resultat=stage.commande(['systemctl','show','mrjam-sauvegarde.service','-p','Result','--value'],d).decode().strip()
    exiger(resultat=='success','Sauvegarde actuelle refusée')
    qualifier_retour_independant(d,stage)
    exiger(stage.etat(d)==avant,'Bascule concurrente')
    if not activer:
        ecrire(d/'preparation.json',{'generation':generation,'sauvegarde_et_restauration':True,'retour_independant':True,'activation':False})
        print(json.dumps({'preparation':True,'generation':generation,'activation':False}));return
    etat=dict(plan,avant=avant,candidat=generation,pids=processus)
    ecrire(d/'plan.json',etat)
    timer='mrjam-reconnexion-retour-'+d.name[:12]
    stage.commande(['systemd-run','--unit='+timer,'--on-active=5min',
        '/run/current-system/sw/bin/nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3','--run',
        'python3 -B '+str(payload/'promouvoir.py')+' retour-automatique '+d.name],d)
    try:
        stage.commande(['systemctl','stop','mrjam-metier'],d)
        postgres=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--json','--expr',
            '(import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ '+json.dumps(avant['configuration_cible'])+' ]; }).config.services.postgresql.finalPackage.outPath'],d))
        def donnees():
            return {b:backup.schema(lambda q,b=b:backup.sql(Path(postgres)/'bin',Path('/run/postgresql'),b,q))
                    for b in ('vision','matheval')}
        reference=donnees();clients=registre_clients();ecrire(d/'donnees-avant-privees.json',reference)
        configuration(str(cfg))
        stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',generation],d)
        stage.commande([generation+'/bin/switch-to-configuration','switch'],d)
        stage.commande(['systemctl','start','mrjam-metier'],d)
        exiger(donnees()==reference,'Invariants métier différents')
        exiger(registre_clients()==clients,'Registre des clients OAuth différent')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation,'Activation non constatée')
        maintenant=pids(stage,d)
        exiger(all(maintenant[n]==pid for n,pid in processus.items() if n!='mrjam-metier'),'Service protégé redémarré')
        exiger(sha(Path('/proc')/maintenant['mrjam-metier']/'exe')==plan['artefact_sha256'],'Binaire servi différent')
        stage.commande(['systemctl','is-active','mrjam-metier','kanidm','nginx','postgresql'],d)
        sonder(plan)
        # Le redémarrage vérifie aussi la persistance des clients historiques.
        stage.commande(['systemctl','restart','mrjam-metier'],d)
        sonder(plan)
        exiger(registre_clients()==clients and donnees()==reference,'Persistance différente après redémarrage')
        exiger(sha(Path('/proc')/pids(stage,d)['mrjam-metier']/'exe')==plan['artefact_sha256'],'Binaire après redémarrage différent')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation,'Retour ou bascule concurrente')
        stage.commande(['systemctl','stop',timer+'.timer'],d)
        preuve={'format':1,'revision_sources':plan['revision_sources'],'generation':generation,
            'artefact_sha256':plan['artefact_sha256'],'site_sha256':plan['site_sha256'],
            'elm_ui_et_animator_servis':True,'tiers_et_kanidm_preserves':True,'schema_et_comptes_non_modifies':True,
            'sauvegarde_actuelle_reussie':True,'restauration_actuelle_isolee_reussie':True,
            'invariants_metier_identiques':True,'retour_code_disponible':True,
            'retour_independant_reel':True,'clients_oauth_preserves':len(clients),
            'persistance_apres_redemarrage':True}
        ecrire(d/'termine.json',preuve);print(json.dumps(preuve))
    except Exception:
        retour(d,stage,etat);stage.commande(['systemctl','stop',timer+'.timer'],d);raise


if __name__=='__main__':
    import fcntl
    exiger(len(sys.argv)==3 and sys.argv[1] in ('promouvoir','preparer','retour','retour-automatique','diagnostic') and re.fullmatch('[a-f0-9]{40}',sys.argv[2]),'Commande refusée')
    d=ROOT/sys.argv[2]
    if sys.argv[1]=='diagnostic':
        plan=json.loads((d/'candidat.json').read_text());stage=charger_stage(plan)
        if not (d/'termine.json').exists() or (d/'retour.json').exists():
            actuel=stage.etat(d)
            print(json.dumps({'generation':actuel['generation'],'demarrage':actuel['demarrage'],
                'code_actif_sha256':sha(Path('/proc')/pids(stage,d)['mrjam-metier']/'exe'),
                'preparation':(d/'preparation.json').exists(),'activation_engagee':(d/'plan.json').exists(),
                'retour':(d/'retour.json').exists(),'termine':False}))
            if (d/'evaluation-reconnexion.json').exists():
                e=json.loads((d/'evaluation-reconnexion.json').read_text())
                print(json.dumps({k:e[k] for k in ('avant','apres','invariants','assertions','nativeActif')}))
            sys.exit(0)
        plan=json.loads((d/'plan.json').read_text())
        exiger((d/'termine.json').exists() and not (d/'retour.json').exists(),'Promotion non active')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==plan['candidat'],'Génération différente')
        exiger(sha(Path('/proc')/pids(stage,d)['mrjam-metier']/'exe')==plan['artefact_sha256'],'Binaire différent')
        sonder(plan);print((d/'termine.json').read_text());sys.exit(0)
    if sys.argv[1]=='retour-automatique':
        if (d/'termine.json').exists():sys.exit(0)
        subprocess.run(['systemctl','stop','mrjam-reconnexion-promotion-'+d.name[:12]+'.service'],check=True)
        plan=json.loads((d/'plan.json').read_text());retour(d,charger_stage(plan),plan);sys.exit(0)
    with open('/root/mrjam-log.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.argv[1] in ('promouvoir','preparer'):promouvoir(d,activer=sys.argv[1]=='promouvoir')
        else:
            plan=json.loads((d/'plan.json').read_text());retour(d,charger_stage(plan),plan)
