"""Promotion Audition : migration additive, client OIDC existant et même serveur commun.

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

ROOT=Path('/root/mrjam-corrections/audition')


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
    return module('stage_audition',Path('/root/mrjam-corrections/audition')/plan['revision_sources']/'payload/preparer.py')


def pids(stage,d):
    return {n:stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip()
            for n in (*stage.TIERS,'kanidm','postgresql','mrjam-metier')}


def retour(d,stage,plan):
    exiger(stage.etat(d)['generation'] in (plan['avant']['generation'],plan['candidat']),'Bascule concurrente')
    configuration(plan['avant']['configuration_lien'] or plan['avant']['configuration_cible'])
    stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',plan['avant']['generation']],d)
    stage.commande([plan['avant']['generation']+'/bin/switch-to-configuration','switch'],d)
    ecrire(d/'retour.json',{'code_seul':True,'donnees_et_identites_non_restaurees':True})


def configurer_retour_oidc(api,d):
    """Raccord officiel borné ; aucun compte personnel ni secret client modifié."""
    operateur=api.login('idm_admin',api.recuperer('idm_admin'),d)
    try:
        avant=api.http('/v1/oauth2/mrjam-vision',token=operateur)['attrs']
        retours=avant['oauth2_rs_origin']
        exiger('https://vision.mrj.am/auth/retour' in retours,'Retour Vision absent')
        secret=api.http('/v1/oauth2/mrjam-vision/_basic_secret',token=operateur)
        exiger(secret==Path('/var/lib/mrjam-identite/kanidm-vision.secret').read_text().strip(),'Secret client différent')
        ajout='https://audition.mrj.am/auth/retour'
        if ajout not in retours:
            api.http('/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin',retours+[ajout],token=operateur)
        apres=api.http('/v1/oauth2/mrjam-vision',token=operateur)['attrs']
        exiger(set(apres['oauth2_rs_origin'])==set(retours+[ajout]),'Retours existants modifiés')
        exiger(api.http('/v1/oauth2/mrjam-vision/_basic_secret',token=operateur)==secret,'Secret client modifié')
    finally: api.commande('disable-account','idm_admin')


def migrer_audition(d,backup,postgres):
    bin=Path(postgres)/'bin';socket=Path('/run/postgresql')
    def sql(q):return backup.sql(bin,socket,'vision',q)
    # Choix opérateur fermé : seul administrateur actif déjà rattaché à Log.
    comptes=json.loads(sql("SELECT coalesce(json_agg(json_build_object('acteur',c.utilisateur,'sujet',i.sujet)),'[]') FROM vision_gestion.comptes c JOIN vision_gestion.identites i USING(utilisateur) WHERE c.actif AND c.administrateur AND i.emetteur='https://log.mrj.am/oauth2/openid/mrjam-vision'"))
    exiger(len(comptes)==1 and re.fullmatch('[A-Za-z0-9_.-]{1,64}',comptes[0]['acteur']),'Administrateur central unique requis')
    present=sql("SELECT to_regnamespace('audition') IS NOT NULL")
    if present=='f':
        sql((d/'payload/001-schema.sql').read_text())
        sql((d/'payload/roles.sql').read_text())
        acteur=comptes[0]['acteur'] # Validé ASCII ci-dessus ; jamais fourni par un client.
        sql("INSERT INTO audition.administrateurs(acteur,actif) VALUES('"+acteur+"',true)")
        sql("INSERT INTO audition.audit(auteur,operation,cible,recu_a,details) VALUES('"+acteur+"','administration_initiale','"+acteur+"',now(),'{\"origine\":\"administrateur_central_Log_unique\"}'::jsonb)")
    exiger(sql('SELECT count(*)=1 AND min(version)=1 FROM audition.schema_migrations')=='t','Schéma Audition différent')
    exiger(sql("SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole FROM pg_roles WHERE rolname='audition_app'")=='t','Rôle Audition trop puissant')
    exiger(sql("SELECT count(*)=6 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='audition' AND t.relname IN ('groupes','objets','versions','requetes','membres','administrateurs') AND t.relrowsecurity AND pg_get_userbyid(t.relowner)<>'audition_app'")=='t','RLS ou propriétaire Audition différents')


def qualifier_retour_independant(d,stage):
    """Précondition réelle du timer : processus temporaire, aucune donnée métier."""
    import time
    marque=d/'retour-independant-temoin'
    if marque.exists():
        exiger(marque.read_text()=='retour-independant','Témoin du retour différent')
        return # Même payload vérifié et même opération, qualifiée en préparation.
    travail='mrjam-audition-temoin-'+d.name[:12]
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
    module_interface=payload/'module.nix';evaluation=payload/'evaluation.nix';module_audition=payload/'audition.nix'
    expression='import '+str(evaluation)+' { configuration='+json.dumps(avant['configuration_cible'])+'; moduleInterface='+json.dumps(str(module_interface))+'; moduleAudition=builtins.toPath '+json.dumps(str(module_audition))+'; site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-audition"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }'
    r=json.loads(stage.commande(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--json','--expr',expression],d))
    exiger(r['avant']==avant['generation'] and r['invariants'] and r['assertions'] and r['nativeActif'],'Configuration hors périmètre')
    exiger(r['paquetApres']==plan['paquet_metier'],'Autre paquet métier')
    ecrire(d/'evaluation-audition.json',r)
    cfg=d/'configuration.nix'
    cfg.write_text('{ lib, ... }: let b=(import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ '+json.dumps(avant['configuration_cible'])+' ]; }).config; in { imports = [ '+json.dumps(avant['configuration_cible'])+' (import '+str(module_interface)+' { authentication=b.services.postgresql.authentication; timers=b.systemd.timers; units=b.systemd.units; moduleAudition=builtins.toPath '+json.dumps(str(module_audition))+'; site=builtins.path { path='+json.dumps(str(site))+'; name="mrjam-audition"; }; paquetMetier=builtins.storePath '+json.dumps(plan['paquet_metier'])+'; }) ]; }\n')
    gcroot=Path('/nix/var/nix/gcroots/mrjam-audition')/d.name;gcroot.parent.mkdir(parents=True,exist_ok=True)
    generation=stage.commande(['nix-build','<nixpkgs/nixos>','-A','system','-I','nixpkgs='+stage.NIXPKGS,
        '-I','nixos-config='+str(cfg),'--out-link',gcroot,'--max-jobs','1','--cores','2'],d).decode().strip()
    exiger(generation==r['apres'],'Génération différente de l’évaluation')
    exiger(Path(r['exeApres']).read_text()==Path(r['exeAvant']).read_text().replace(r['paquetAvant'],r['paquetApres']),
           'Autre changement du script de démarrage')
    nginx=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+/bin/nginx',r['nginx'])
    configs=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+\.conf',r['nginx'])
    exiger(len(nginx)==len(configs)==1,'Configuration Nginx ambiguë')
    # Nouveau nom : le vrai certificat sera émis par les unités ACME centrales
    # lors de l'activation. Ici seule la syntaxe est vérifiée ; le candidat
    # original reste immuable et les sondes finales exigent son HTTPS valide.
    controle=configs[0]
    if not Path('/var/lib/acme/audition.mrj.am/fullchain.pem').is_file():
        source=Path(controle).read_text()
        exiger('/var/lib/acme/audition.mrj.am/' in source and Path('/var/lib/acme/log.mrj.am/fullchain.pem').is_file(),
               'Précondition de contrôle TLS absente')
        controle=d/'nginx-syntaxe-audition.conf'
        controle.write_text(source.replace('/var/lib/acme/audition.mrj.am/','/var/lib/acme/log.mrj.am/'))
    stage.commande([nginx[0],'-t','-c',controle],d)
    processus=pids(stage,d)
    exiger(sha(Path('/proc')/processus['mrjam-metier']/'exe')==plan['artefact_avant'],'Code actif différent')
    # Restauration actuelle isolée avec le mécanisme central déjà qualifié.
    # Aucun schéma/format ne change ; le retour garde les données courantes.
    backup=module('backup_audition',payload/'sauvegarde.py')
    backup.GENERATION=avant['generation'];backup.main(d.name,sqlite_reprise={'log-native':'/var/lib/mrjam-metier/log/sessions.sqlite'})
    stage.commande(['systemctl','start','mrjam-sauvegarde.service'],d)
    resultat=stage.commande(['systemctl','show','mrjam-sauvegarde.service','-p','Result','--value'],d).decode().strip()
    exiger(resultat=='success','Sauvegarde actuelle refusée')
    qualifier_retour_independant(d,stage)
    exiger(stage.etat(d)==avant,'Bascule concurrente')
    if not activer:
        ecrire(d/'preparation-audition.json',{'generation':generation,'preconditions_sauvegarde_restaurations':True,'activation':False})
        print(json.dumps({'preparation':True,'generation':generation,'activation':False}));return
    etat=dict(plan,avant=avant,candidat=generation,pids=processus)
    ecrire(d/'plan.json',etat)
    timer='mrjam-audition-retour-'+d.name[:12]
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
        reference=donnees();ecrire(d/'donnees-avant-privees.json',reference)
        migrer_audition(d,backup,postgres)
        natif=module('api_native_audition',payload/'native.py')
        match=re.findall(r'/nix/store/[a-z0-9]{32}-server\.toml',r['kanidmCommande'])
        exiger(len(match)==1,'Configuration native ambiguë')
        api=natif.KanidmPrive(plan['paquet_kanidm'],match[0],Path(plan['outils'])/'curl/bin/curl')
        configurer_retour_oidc(api,d)
        configuration(str(cfg))
        stage.commande(['nix-env','-p','/nix/var/nix/profiles/system','--set',generation],d)
        stage.commande([generation+'/bin/switch-to-configuration','switch'],d)
        stage.commande(['systemctl','start','mrjam-metier'],d)
        apres=donnees()
        exiger(all({k:v for k,v in apres[b].items() if not k.startswith('audition.')}==
                    {k:v for k,v in reference[b].items() if not k.startswith('audition.')} for b in reference),
               'Invariants métier existants différents')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation,'Activation non constatée')
        maintenant=pids(stage,d)
        exiger(all(maintenant[n]==pid for n,pid in processus.items() if n!='mrjam-metier'),'Service protégé redémarré')
        exiger(sha(Path('/proc')/maintenant['mrjam-metier']/'exe')==plan['artefact_sha256'],'Binaire servi différent')
        stage.commande(['systemctl','is-active','mrjam-metier','kanidm','nginx','postgresql'],d)
        import time
        limite=time.monotonic()+90
        while True:
            try:
                with urllib.request.urlopen('https://audition.mrj.am/',timeout=10) as response:
                    exiger(response.status==200 and hashlib.sha256(response.read(4*1024*1024+1)).hexdigest()==plan['site_fichiers']['index.html'],
                           'Landing réelle différente')
                break
            except (urllib.error.URLError,TimeoutError):
                exiger(time.monotonic()<limite,'HTTPS Audition non établi')
                time.sleep(1)
        for rel,h in plan['site_fichiers'].items():
            url='https://audition.mrj.am/'+('' if rel=='index.html' else rel)
            with urllib.request.urlopen(url,timeout=20) as response:
                exiger(response.status==200 and hashlib.sha256(response.read(4*1024*1024+1)).hexdigest()==h,'Ressource servie différente')
        exiger(stage.etat(d)['generation']==stage.etat(d)['demarrage']==generation,'Retour ou bascule concurrente')
        stage.commande(['systemctl','stop',timer+'.timer'],d)
        preuve={'format':1,'revision_sources':plan['revision_sources'],'generation':generation,
            'artefact_sha256':plan['artefact_sha256'],'site_sha256':plan['site_sha256'],
            'elm_ui_et_animator_servis':True,'tiers_et_kanidm_preserves':True,'schema_audition_additif':True,
            'comptes_et_schemas_existants_preserves':True,'client_oidc_secret_et_retours_preserves':True,
            'sauvegarde_actuelle_reussie':True,'restauration_actuelle_isolee_reussie':True,
            'invariants_metier_existants_identiques':True,'retour_code_disponible':True,'retour_independant_reel':True}
        ecrire(d/'termine.json',preuve);print(json.dumps(preuve))
    except Exception:
        retour(d,stage,etat);stage.commande(['systemctl','stop',timer+'.timer'],d);raise


if __name__=='__main__':
    import fcntl
    exiger(len(sys.argv)==3 and sys.argv[1] in ('promouvoir','preparer','retour','retour-automatique') and re.fullmatch('[a-f0-9]{40}',sys.argv[2]),'Commande refusée')
    if sys.argv[1]=='retour-automatique':
        d=ROOT/sys.argv[2]
        if (d/'termine.json').exists():sys.exit(0)
        # Le retour ne dépend pas du verrou détenu par une promotion suspendue.
        subprocess.run(['systemctl','stop','mrjam-audition-promotion-'+d.name[:12]+'.service'],check=True)
        plan=json.loads((d/'plan.json').read_text());r=json.loads((d/'evaluation-audition.json').read_text())
        natif=module('api_native_retour',d/'payload/native.py')
        match=re.findall(r'/nix/store/[a-z0-9]{32}-server\.toml',r['kanidmCommande'])
        if len(match)==1:
            api=natif.KanidmPrive(plan['paquet_kanidm'],match[0],Path(plan['outils'])/'curl/bin/curl')
            try:api.commande('disable-account','idm_admin')
            except natif.OperationRefusee:pass
        retour(d,charger_stage(plan),plan)
        sys.exit(0)
    with open('/root/mrjam-audition.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        d=ROOT/sys.argv[2]
        if sys.argv[1] in ('promouvoir','preparer'):promouvoir(d,activer=sys.argv[1]=='promouvoir')
        elif not (d/'termine.json').exists():
            plan=json.loads((d/'plan.json').read_text());retour(d,charger_stage(plan),plan)
