"""Bascule courte et retour du code ; jamais de restauration ancienne de SQL.

Écritures métier arrêtées pendant le transfert SQLite/JSONL. Les bases restent
en place. Un retour indépendant est armé avant la bascule et retiré seulement
après les contrôles de l'artefact servi et du redémarrage.
"""
import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]
METIER=('vision','matheval','vision-migrate','vision-gestion','vision-cycle',
        'mrjam-admission','mrjam-fermeture','mrjam-courriel','vision-purge')
TIMERS=('vision-purge.timer','mrjam-courriel.timer')
DESTINATIONS={'cycle-courriels':'cycle/courriels.sqlite','admissions':'admission/admissions.sqlite',
 'admission-courriels':'admission/courriels.sqlite','fermeture-courriels':'fermeture/courriels.sqlite',
 'courriel':'courriel/file.sqlite','effacements':'effacements/demandes.jsonl',
 'effacements-cycle':'cycle/effacements.jsonl','effacements-fermeture':'fermeture/effacements.jsonl'}
ETAT_METIER=Path('/var/lib/mrjam-metier')
PORTE=Path('/run/systemd/system/mrjam-metier.service.d/90-assemblage.conf')


def module(n,path):
    s=importlib.util.spec_from_file_location(n,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


stage=module('mrjam_preparer_activer',ROOT/'scripts/monolithe-preparer.py')
backup=module('mrjam_sauvegarde_activer',ROOT/'scripts/monolithe-sauvegarde.py')


def ecrire(path,objet):
    temporaire=path.with_suffix('.tmp')
    with temporaire.open('w') as f:
        json.dump(objet,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temporaire,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def proprietes(p):
    s=p.lstat();stage.exiger(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'État non régulier')
    return {'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode)}


def copie(source,cible,identite):
    stage.exiger(not source.is_symlink(),'Source redirigée')
    cible.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=cible.with_name(cible.name+'.assemblage-copie')
    stage.exiger(not tmp.exists() and not cible.is_symlink(),'Copie concurrente ou cible redirigée')
    if source.suffix=='.sqlite':backup.copie_sqlite(source,tmp)
    else:backup.copie_registre(source,tmp)
    os.chown(tmp,identite['uid'],identite['gid']);tmp.chmod(identite['mode'])
    with tmp.open('rb') as f:os.fsync(f.fileno())
    os.replace(tmp,cible)
    fd=os.open(cible.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def changer_configuration(cible):
    p=Path('/etc/nixos/configuration.nix');t=p.with_name('configuration.nix.mrjam-candidat')
    stage.exiger(not t.exists() and not t.is_symlink(),'Configuration concurrente')
    t.symlink_to(cible);os.replace(t,p)


def changer_publication(p,cible,attendu):
    stage.exiger(p.is_symlink() and str(p.resolve())==attendu,'Publication concurrente ou non symbolique')
    tmp=p.with_name(p.name+'.mrjam-assemblage')
    stage.exiger(not tmp.exists() and not tmp.is_symlink(),'Publication concurrente')
    tmp.symlink_to(cible);os.replace(tmp,p)


def controle(d,prepare,cert,*,redemarrer=False):
    stage.commande(['systemctl','is-active','mrjam-metier','nginx','postgresql',*stage.TIERS],d)
    pid=stage.commande(['systemctl','show','mrjam-metier','-p','MainPID','--value'],d).decode().strip()
    stage.exiger(pid.isdigit() and int(pid)>0,'PID métier absent')
    stage.exiger(stage.sha(Path('/proc')/pid/'exe')==cert['qualification']['artefact_sha256'],'Artefact servi différent')
    for n in METIER:
        p=stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).decode().strip()
        stage.exiger(p in ('','0'),'Ancien processus métier encore actif : '+n)
    actuel=stage.etat(d)
    stage.exiger(actuel['tiers_pids']==prepare['avant']['tiers_pids'],'Processus tiers redémarré')
    reference=module('mrjam_reference_activer',ROOT/'scripts/monolithe-reference.py')
    for u,codes in [('https://principiipetit.io/matheval/api/health',(200,)),
                    ('https://vision.mrj.am/',(200,)),('https://vision.mrj.am/mcp',(401,)),
                    ('https://log.mrj.am/realms/mrjam/.well-known/openid-configuration',(200,)),
                    ('https://logique.echos.systems/',(200,))]:reference.latence(u,codes)
    # Sonde de falsification publique : un navigateur ne fabrique pas l'identité.
    import urllib.request,urllib.error
    req=urllib.request.Request('https://vision.mrj.am/api/v1/lire',data=b'{"type":"item","ids":[]}',
        headers={'Content-Type':'application/json','X-Vision-Authenticated':'1','X-Mrj-User':'alice'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:code=r.status
    except urllib.error.HTTPError as e:code=e.code
    stage.exiger(code in (401,403),'Identité publique falsifiable')
    if redemarrer:
        stage.commande(['systemctl','restart','mrjam-metier'],d)
        for _ in range(100):
            if subprocess.run(['systemctl','is-active','--quiet','mrjam-metier']).returncode==0:break
            time.sleep(.1)
        else:raise ValueError('Redémarrage refusé')
        controle(d,prepare,cert)
    for n,url,p in [('vision','https://vision.mrj.am/app.js','app.js'),
                    ('matheval','https://principiipetit.io/matheval/enquete.js','enquete.js'),
                    ('logique','https://logique.echos.systems/app.js','app.js')]:
        with urllib.request.urlopen(url,timeout=20) as r:
            stage.exiger(r.status==200,'Ressource publique indisponible')
            import hashlib
            stage.exiger(hashlib.sha256(r.read(16*1024*1024+1)).hexdigest()==cert['frontends'][n]['fichiers'][p],
                         'Ressource servie différente du candidat : '+n)


def retour(d,prepare,plan):
    if (d/'retour.json').exists():
        stage.exiger(stage.etat(d)==prepare['avant'],'État différent après le retour enregistré')
        return
    # Avant la génération candidate, cette unité peut ne pas exister. Un arrêt
    # refusé d'une unité présente reste une erreur ; on ne masque pas son code.
    charge=stage.commande(['systemctl','show','mrjam-metier','-p','LoadState','--value'],d).decode().strip()
    if charge!='not-found':stage.commande(['systemctl','stop','mrjam-metier'],d)
    # Le nouveau serveur arrêté a pu ajouter des lignes : copier ses dernières
    # données vers les chemins historiques, jamais les copies d'avant bascule.
    if plan.get('phase') in ('etats-transferes','service-demarre','qualification'):
        for n,ancien in plan['etats'].items():
            source=ETAT_METIER/DESTINATIONS[n]
            if source.exists():copie(source,Path(stage.ETATS[n]),ancien)
    if plan.get('publication_logique_avant'):
        p=Path(prepare['avant']['publications']['logique'])
        courant=str(p.resolve());ancien=prepare['avant']['cibles']['logique']
        if courant!=ancien:
            stage.exiger(courant==str(Path('/srv/mrjam-assemblages')/d.name/'logique'),'Publication Logique concurrente')
            changer_publication(p,plan['publication_logique_avant'],courant)
    changer_configuration(prepare['avant']['configuration_lien'] or prepare['avant']['configuration_cible'])
    stage.commande([Path(prepare['avant']['generation'])/'bin/switch-to-configuration','test'],d)
    stage.commande(['nix-env','--profile','/nix/var/nix/profiles/system','--set',prepare['avant']['generation']],d)
    PORTE.unlink(missing_ok=True)
    stage.commande(['systemctl','daemon-reload'],d)
    units=[n for n,v in plan.get('unites_avant',{}).items() if v=='active']
    if units:stage.commande(['systemctl','start',*units],d)
    stage.exiger(stage.etat(d)==prepare['avant'],'Retour différent de la référence ; vérifier le diagnostic privé')
    ecrire(d/'retour.json',{'format':1,'revision':d.name,'retour_code':True,
        'restauration_ancienne_sql':False,'derniers_etats_durables_recopies':True})
    stage.commande(['systemctl','stop','mrjam-retour-'+d.name[:12]+'.timer'],d)


def activer(d,prepare,cert):
    stage.exiger(stage.etat(d)==prepare['avant'],'État concurrent depuis préparation')
    r=json.loads((d/'restauration.json').read_text());q=r['qualification_applicative']
    stage.exiger(r['empreintes_semantiques_identiques'] and r['retour_applicatif_qualifie']
                 and q['acl_vision_30_matheval_6'] and not q['retour_operations_ecriture_restant'],
                 'Restauration/retour non qualifiés')
    stage.exiger(time.time()-(d/'restauration.json').stat().st_mtime<900,'Sauvegarde de transition trop ancienne')
    stage.exiger(not (d/'activation.json').exists() and not (d/'termine.json').exists(),'Activation déjà engagée')
    plan={'format':1,'phase':'preconditions','revision':d.name,'etats':{},'unites_avant':{}}
    for n in (*METIER,*TIMERS):
        plan['unites_avant'][n]=stage.commande(['systemctl','show',n,'-p','ActiveState','--value'],d).decode().strip()
    for n,p in stage.ETATS.items():
        if Path(p).exists():plan['etats'][n]=proprietes(Path(p))
    ecrire(d/'activation.json',plan)
    unit='mrjam-retour-'+d.name[:12]
    cmd='python3 '+str(ROOT/'scripts/monolithe-activer.py')+' retour-auto '+d.name
    stage.commande(['systemd-run','--unit='+unit,'--on-active=15m','--timer-property=AccuracySec=1s',
        '--property=Restart=on-failure','--property=RestartSec=30s','--property=StartLimitIntervalSec=0',
        'nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3','--run',cmd],d)
    try:
        actifs=[n for n,v in plan['unites_avant'].items() if v in ('active','activating')]
        if actifs:stage.commande(['systemctl','stop',*actifs],d)
        plan['phase']='anciens-arretes';ecrire(d/'activation.json',plan)
        evaluation=json.loads((d/'evaluation-privee.json').read_text());pg=Path(evaluation['postgres'])/'bin'
        def sql(b,t):return backup.sql(pg,Path('/run/postgresql'),b,t)
        invariants={b:backup.schema(lambda t,b=b:sql(b,t)) for b in ('vision','matheval')}
        (d/'invariants-avant-prives.json').write_text(json.dumps(invariants,indent=2)+'\n')
        v=sql('vision','SELECT max(version) FROM vision_schema_migrations')
        stage.exiger(v in ('25','26'),'Schéma Vision inattendu')
        if v=='25':sql('vision',(d/'payload/vision/migrations/026_autorisation_admission.sql').read_text())
        sql('vision',(d/'payload/vision/scripts/roles.sql').read_text())
        stage.commande(['runuser','-u','postgres','--',pg/'psql','-Xq','--set=ON_ERROR_STOP=1','--file',ROOT/'assemblage/roles-metier.sql'],d)
        gate=PORTE
        gate.parent.mkdir(parents=True,exist_ok=True)
        stage.exiger(not gate.exists(),'Porte de démarrage concurrente')
        gate.write_text('[Unit]\nConditionPathExists='+str(d/'etats-prets')+'\n')
        stage.commande(['systemctl','daemon-reload'],d)
        stage.commande([Path(prepare['candidat'])/'bin/switch-to-configuration','test'],d)
        stage.exiger(stage.commande(['systemctl','show','mrjam-metier','-p','MainPID','--value'],d).decode().strip()=='0','Démarrage avant transfert')
        user=pwd.getpwnam('mrjam-metier');base=ETAT_METIER
        base.mkdir(mode=0o700,exist_ok=True);os.chown(base,user.pw_uid,user.pw_gid);base.chmod(0o700)
        for n,props in plan['etats'].items():
            cible=base/DESTINATIONS[n]
            stage.exiger(not cible.exists(),'État cible déjà présent ; reprise explicite requise')
            copie(Path(stage.ETATS[n]),cible,{'uid':user.pw_uid,'gid':user.pw_gid,'mode':0o600})
        for p in base.rglob('*'):
            stage.exiger(not p.is_symlink(),'Lien dans les états cibles')
            if p.is_dir():os.chown(p,user.pw_uid,user.pw_gid);p.chmod(0o700)
        secret=Path('/var/lib/matheval/secrets.env').read_text()
        lignes=[l.removeprefix('ADMIN_SETUP_TOKEN_HASH=') for l in secret.splitlines() if l.startswith('ADMIN_SETUP_TOKEN_HASH=')]
        stage.exiger(len(lignes)==1 and re.fullmatch('[a-f0-9]{64}',lignes[0]),'Empreinte setup inattendue')
        secrets=base/'secrets';secrets.mkdir(mode=0o700,exist_ok=True)
        (secrets/'matheval-setup-hash').write_text(lignes[0]+'\n');(secrets/'matheval-setup-hash').chmod(0o600)
        plan['phase']='etats-transferes';ecrire(d/'activation.json',plan)
        publication=Path(prepare['avant']['publications']['logique'])
        stage.exiger(publication.is_symlink(),'Publication Logique non symbolique')
        plan['publication_logique_avant']=os.readlink(publication);ecrire(d/'activation.json',plan)
        changer_publication(publication,str(Path('/srv/mrjam-assemblages')/d.name/'logique'),prepare['avant']['cibles']['logique'])
        changer_configuration(prepare['configuration'])
        stage.commande(['nix-env','--profile','/nix/var/nix/profiles/system','--set',prepare['candidat']],d)
        (d/'etats-prets').write_text('1\n')
        stage.commande(['systemctl','start','mrjam-metier'],d)
        plan['phase']='service-demarre';ecrire(d/'activation.json',plan)
        controle(d,prepare,cert,redemarrer=True)
        apres={b:backup.schema(lambda t,b=b:sql(b,t)) for b in ('vision','matheval')}
        invariants['vision'].pop('public.vision_schema_migrations',None);apres['vision'].pop('public.vision_schema_migrations',None)
        stage.exiger(invariants==apres,'Données modifiées pendant la bascule : qualification privée requise')
        gate.unlink();stage.commande(['systemctl','daemon-reload'],d)
        ecrire(d/'termine.json',{'format':1,'revision':d.name,'generation':prepare['candidat'],
           'artefact_sha256':cert['qualification']['artefact_sha256'],'donnees_preservees':True,
           'redemarrage_verifie':True,'processus_metier':1,'keycloak_conserve':True,
           'mcp_anonyme_refuse':True,'mcp_client_personnel_non_reautorise':True})
        stage.commande(['systemctl','stop',unit+'.timer'],d)
        print(json.dumps(json.loads((d/'termine.json').read_text()),ensure_ascii=False))
    except Exception:
        (d/'erreur-activation-privee.log').write_text(traceback.format_exc())
        retour(d,prepare,plan)
        raise RuntimeError('Bascule refusée ; retour du code effectué, détails privés')


def main(operation,revision):
    stage.exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision),'Opérateur refusé')
    os.umask(0o077);d=Path('/root/mrjam-assemblages')/revision
    prepare=json.loads((d/'preparation.json').read_text());cert=stage.verifier_bundle(d/'payload')
    with open('/root/mrjam-assemblage.lock','a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if operation=='activer':activer(d,prepare,cert)
        elif operation in ('retour','retour-auto'):
            if operation=='retour-auto' and (d/'termine.json').exists():return
            retour(d,prepare,json.loads((d/'activation.json').read_text()))
        else:raise ValueError('Opération inconnue')


if __name__=='__main__':
    try:main(sys.argv[1],sys.argv[2])
    except Exception:
        print('Opération refusée ; vérifier le diagnostic privé sur le VPS.',file=sys.stderr);sys.exit(1)
