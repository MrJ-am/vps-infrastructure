"""Bascule fermée Log, invitation propriétaire et retour des seules identités.

Aucune restauration de base métier. Les secrets, adresses et liens d'enrôlement
restent sur le VPS ; seule une preuve agrégée est publiée.
"""
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shlex
import sqlite3
import stat
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PHASE='demarrage'
NEW_ISSUER='https://log.mrj.am/oauth2/openid/mrjam-vision'

def module(nom,fichier):
    s=importlib.util.spec_from_file_location(nom,ROOT/fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

stage=module('log_stage','scripts/monolithe-preparer.py')
base=module('log_backup','scripts/monolithe-sauvegarde.py')
native=module('log_native','scripts/kanidm-api-privee.py')

def exiger(v,msg):
    if not v: raise ValueError(msg)

def ecrire(p,d):
    tmp=p.with_name(p.name+'.nouveau')
    with tmp.open('w') as f:
        json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    tmp.chmod(0o600);os.replace(tmp,p)
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def lire_prive(p,limite=65536):
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        exiger(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and
               not st.st_mode&0o077 and st.st_size<=limite,'Fichier opérateur non privé')
        return os.read(fd,limite+1)
    finally: os.close(fd)

def sql(texte):
    return json.loads(subprocess.run(['runuser','-u','postgres','--','psql','-XAtq',
        '--set=ON_ERROR_STOP=1','--dbname=vision'],input=texte,capture_output=True,text=True,check=True,timeout=30).stdout)

def quote(s): return "'"+s.replace("'","''")+"'"

def donnees():
    def projection(b): return base.schema(lambda q: base.sql(Path('/run/current-system/sw/bin'),Path('/run/postgresql'),b,q))
    # La liaison d'authentification est le seul changement métier attendu.
    v=projection('vision'); v.pop('vision_gestion.identites',None)
    return {'vision':v,'matheval':projection('matheval')}

class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def ancien_operateur():
    controle=module('log_kc_controle','scripts/identite-amorcage-controle.py')
    secret=lire_prive('/var/lib/mrjam-identite/amorcage-admin.secret',128).decode().strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),SansRedirection())
    token=controle.api(opener,'/realms/master/protocol/openid-connect/token',formulaire={
        'grant_type':'password','client_id':'admin-cli','username':'amorcage-local','password':secret})['access_token']
    anciennes=module('log_kc_api','scripts/vision-proprietaire-enroler.py')
    return anciennes.ApiPrivee(token)

def inventorier_ancien(api):
    realms=api('/admin/realms')
    exiger(isinstance(realms,list) and {r.get('realm') for r in realms}=={'master','mrjam'},
           'Realm IdP supplémentaire à préserver')
    realm=api('/admin/realms/mrjam/')
    exiger(set(realm.get('eventsListeners',[])) <= {'jboss-logging'}, 'Hook IdP supplémentaire à neutraliser')
    clients=api('/admin/realms/mrjam/clients')
    autorises={'account','account-console','admin-cli','broker','realm-management','security-admin-console',
               'mrjam-vision','mrjam-cycle','mrjam-admission','mrjam-fermeture'}
    exiger(all(x.get('clientId') in autorises for x in clients),'Consommateur IdP supplémentaire à préserver')
    users=api('/admin/realms/mrjam/users?max=100')
    exiger(len(users)<100,'Inventaire IdP tronqué : comptes supplémentaires à vérifier')
    personnels=[u for u in users if not u.get('serviceAccountClientId')]
    exiger(len(personnels)==1 and personnels[0].get('email'), 'Comptes IdP supplémentaires ou adresse absente')
    uuid.UUID(personnels[0]['id'])
    return personnels[0]

def config_native(d,prepare):
    r=json.loads((d/'evaluation-log-privee.json').read_text())
    match=re.findall(r'/nix/store/[a-z0-9]{32}-server\.toml',r['kanidmConfig'])
    exiger(len(match)==1,'Configuration native ambiguë')
    return match[0]

def age(d,cert): return Path(cert['qualification']['sorties_nix']['outils'])/'age/bin/age'

def chiffrer(d,cert,nom,contenu):
    connu=(ROOT/'scripts/ssh-known-hosts').read_text().split()
    r=json.loads((d/'evaluation-log-privee.json').read_text())
    cmd=[age(d,cert),'-r',' '.join(connu[1:]),'-r',r['backupRecipient']]
    with (d/nom).open('xb') as f:
        subprocess.run(cmd,input=contenu,stdout=f,stderr=subprocess.DEVNULL,check=True,timeout=60)

def dechiffrer(d,cert,nom):
    return subprocess.run([age(d,cert),'-d','-i','/etc/ssh/ssh_host_ed25519_key',d/nom],
         capture_output=True,check=True,timeout=60).stdout

def amorcer(d,p,cert):
    global PHASE
    PHASE='inventaire-prive'
    exiger(stage.etat(d)==p['avant'],'État concurrent depuis préparation')
    ancien=ancien_operateur();personne=inventorier_ancien(ancien)
    comptes=sql("SELECT coalesce(json_agg(c),'[]') FROM (SELECT id,utilisateur,actif,administrateur FROM vision_gestion.comptes) c")
    liens=sql("SELECT coalesce(json_agg(i),'[]') FROM vision_gestion.identites i")
    exiger(len(comptes)==len(liens)==1 and comptes[0]['actif'] and comptes[0]['administrateur'] and
        comptes[0]['utilisateur']==liens[0]['utilisateur'],'Propriétaire métier non unique/cohérent')
    exiger(re.fullmatch('[A-Za-z0-9_.-]{1,128}',comptes[0]['utilisateur']),'Propriétaire métier inattendu')
    exiger(sql("SELECT count(*) FROM pg_trigger WHERE tgrelid='vision_gestion.identites'::regclass AND NOT tgisinternal")==0,
           'Hook SQL sur le rattachement à examiner')
    for path in ('admission/admissions.sqlite','fermeture/courriels.sqlite'):
        f=Path('/var/lib/mrjam-metier')/path
        if f.exists():
            with sqlite3.connect(f.as_uri()+'?mode=ro',uri=True) as c:
                if path.startswith('admission/'):
                    exiger(c.execute("SELECT count(*) FROM demandes WHERE etat IN ('attente','provisionnee')").fetchone()[0]==0,
                           'Admissions en cours à porter avant bascule')
                else:
                    exiger(c.execute('SELECT count(*) FROM fermetures WHERE terminee IS NULL').fetchone()[0]==0,
                           'Fermetures en cours à préserver')
    plan=dict(format=1,revision=d.name,phase='inventaire',ancien_compte=comptes[0],ancien_lien=liens[0],
              ancien_idp=personne['id'],mail=personne['email'],name='proprietaire-'+secrets.token_hex(8),
              qualified_after=int(time.time()),donnees=donnees())
    ecrire(d/'activation-log-privee.json',plan)
    PHASE='sauvegarde-identites'
    dump=subprocess.run(['runuser','-u','postgres','--','pg_dump','--format=custom','mrjam_identite'],
                        capture_output=True,check=True,timeout=60).stdout
    exiger(len(dump)<128*1024*1024,'Sauvegarde IdP hors borne')
    chiffrer(d,cert,'identite-retour.dump.age',dump)
    old=Path('/var/lib/vision/auth/htpasswd')
    exiger(old.is_file() and not old.is_symlink() and old.stat().st_size<65536,'Ancien accès inattendu')
    chiffrer(d,cert,'vision-ancienne-auth.age',old.read_bytes())
    PHASE='amorcage-native-loopback'
    stage.commande([Path(p['amorcage'])/'bin/switch-to-configuration','test'],d)
    exiger(str(Path('/run/current-system').resolve())==p['amorcage'],'Amorçage non actif')
    stage.commande(['systemctl','is-active','kanidm','mrjam-metier','keycloak','mrj-auth'],d)
    paquet=cert['qualification']['sorties_nix']['kanidm']
    outils=Path(cert['qualification']['sorties_nix']['outils'])
    api=native.KanidmPrive(paquet,config_native(d,p),outils/'curl/bin/curl')
    PHASE='nouvelle-identite'
    plan['phase']='provisionnement-native-engage';ecrire(d/'activation-log-privee.json',plan)
    result=api.configurer_proprietaire(plan,d)
    uuid.UUID(result['subject'])
    secret=Path('/var/lib/mrjam-identite/kanidm-vision.secret')
    exiger(not secret.exists(),'Credential client natif déjà présent : reprise à constater')
    with secret.open('x') as f: f.write(result['client_secret']+'\n')
    secret.chmod(0o600)
    admission=Path('/var/lib/mrjam-identite/kanidm-admission.token')
    exiger(not admission.exists(),'Capacité admission native déjà présente : reprise à constater')
    with admission.open('x') as f: f.write(result['admission_token']+'\n')
    admission.chmod(0o600)
    plan.update(subject=result['subject'],intent=result['intent'],phase='native-prepare')
    ecrire(d/'activation-log-privee.json',plan)
    # Restaurer réellement le backup natif dans une base indépendante, sans
    # démarrer une seconde identité publique ni créer de comptes synthétiques.
    PHASE='restauration-native-isolee'
    sauvegarde=Path('/var/lib/kanidm')/('transition-'+d.name[:12]+'.json')
    api.commande('scripting','backup',str(sauvegarde))
    contenu=sauvegarde.read_bytes();exiger(0<len(contenu)<128*1024*1024,'Backup natif hors borne')
    chiffrer(d,cert,'kanidm-transition.json.age',contenu)
    backup=d/'restauration-native.json';backup.write_bytes(contenu);backup.chmod(0o600)
    api.restaurer_verifier(backup,d/'restauration-kanidm',plan['subject'])
    sauvegarde.unlink();backup.unlink()
    plan['restauration_native']=True;ecrire(d/'activation-log-privee.json',plan)
    return plan

def seed_log(d,plan):
    p=Path('/var/lib/mrjam-metier/log');p.mkdir(mode=0o700,exist_ok=True)
    uid=pwd.getpwnam('mrjam-metier');os.chown(p,uid.pw_uid,uid.pw_gid)
    f=p/'sessions.sqlite'
    exiger(not f.exists(),'État Log existant : reprise à constater')
    with sqlite3.connect(f) as c:
        c.execute("CREATE TABLE log_principaux(subject TEXT PRIMARY KEY,mail TEXT UNIQUE NOT NULL,duration INTEGER NOT NULL CHECK(duration IN (604800,2592000,7776000)),minimum TEXT NOT NULL CHECK(minimum IN ('any','mfa')),qualified_after INTEGER NOT NULL)")
        c.execute('INSERT INTO log_principaux VALUES(?,?,?,?,?)',(plan['subject'],plan['mail'].lower(),604800,'mfa',plan['qualified_after']))
    f.chmod(0o600);os.chown(f,uid.pw_uid,uid.pw_gid)

def rattacher(plan,retour=False):
    old=plan['ancien_lien']; user=plan['ancien_compte']['utilisateur']
    avant=(NEW_ISSUER,plan['subject']) if retour else (old['emetteur'],old['sujet'])
    apres=(old['emetteur'],old['sujet']) if retour else (NEW_ISSUER,plan['subject'])
    n=sql('BEGIN; WITH x AS (UPDATE vision_gestion.identites SET emetteur='+quote(apres[0])+',sujet='+quote(apres[1])+
          ' WHERE utilisateur='+quote(user)+' AND emetteur='+quote(avant[0])+' AND sujet='+quote(avant[1])+
          ' RETURNING 1) SELECT count(*) FROM x; COMMIT;')
    exiger(n==1,'Rattachement concurrent ou absent')

def retablir_rattachement(plan):
    "Constater l'issue SQL réelle, y compris après timeout après COMMIT."
    actuel=sql('SELECT json_build_object(\'emetteur\',emetteur,\'sujet\',sujet) FROM vision_gestion.identites WHERE utilisateur='+quote(plan['ancien_compte']['utilisateur']))
    if actuel=={'emetteur':NEW_ISSUER,'sujet':plan['subject']}: rattacher(plan,retour=True)
    else: exiger(actuel=={k:plan['ancien_lien'][k] for k in ('emetteur','sujet')},'Rattachement concurrent au retour')

def sonder(d,p,cert,plan):
    reference=module('log_sondes','scripts/monolithe-reference.py')
    stage.commande(['systemctl','is-active','kanidm','mrjam-metier','nginx','postgresql'],d)
    stage.commande(['systemctl','is-active',*[n for n in stage.TIERS if n not in ('keycloak','mrj-auth')]],d)
    for n in ('keycloak','mrj-auth','vision','matheval'):
        exiger(stage.commande(['systemctl','show',n,'-p','MainPID','--value'],d).strip() in (b'',b'0'),'Ancien processus actif')
    pid=stage.commande(['systemctl','show','mrjam-metier','-p','MainPID','--value'],d).decode().strip()
    exiger(hashlib.sha256(Path('/proc',pid,'exe').read_bytes()).hexdigest()==cert['qualification']['artefact_sha256'],'Artefact actif différent')
    with urllib.request.urlopen('https://log.mrj.am/oauth2/openid/mrjam-vision/.well-known/openid-configuration',timeout=15) as r:
        discovery=json.load(r)
    exiger(discovery['issuer']==NEW_ISSUER and discovery['code_challenge_methods_supported']==['S256'],'Découverte active incorrecte')
    for url in ('https://vision.mrj.am/','https://principiipetit.io/matheval/api/health','https://logique.echos.systems/'):
        with urllib.request.urlopen(url,timeout=15) as r:exiger(r.status==200,'Interface publique indisponible')
    ressources=[('vision','https://vision.mrj.am/app.js','app.js'),
                ('logique','https://logique.echos.systems/app.js','app.js')]
    ressources += [('matheval','https://principiipetit.io/matheval/'+f,f) for f in
                   ('main.js','demo-card.js','survey.js','admin/administration.js','enquete.js')]
    for nom,url,fichier in ressources:
        with urllib.request.urlopen(url,timeout=15) as r:
            exiger(hashlib.sha256(r.read(16*1024*1024+1)).hexdigest()==cert['frontends'][nom]['fichiers'][fichier],
                   'Frontend actif différent : '+nom)
    # La sonde ne transporte ni ne consomme l'intent d'invitation personnel.
    # L'intent personnel n'est pas consommé/exchangé par une sonde.
    with urllib.request.urlopen('https://log.mrj.am/ui/reset',timeout=15) as r:
        exiger(r.status==200,'Invitation inaccessible')
    exiger(donnees()==plan['donnees'],'Contenu métier modifié durant bascule')
    actuel=stage.etat(d)
    exiger({n:v for n,v in actuel['tiers_pids'].items() if n not in ('keycloak','mrj-auth')}==
           {n:v for n,v in p['avant']['tiers_pids'].items() if n not in ('keycloak','mrj-auth')},'Service tiers redémarré')
    return {n:reference.memoire(n) for n in ('kanidm','mrjam-metier','keycloak','mrj-auth')}

def envoyer(d,p,cert,plan):
    global PHASE
    PHASE='courriel'
    marque=d/'courriel-log.json'
    if marque.exists():
        ancien=json.loads(marque.read_text())
        exiger(ancien.get('accepte_par_relais') is True,'Envoi précédent incertain : ne pas répéter')
        return ancien
    from email.message import EmailMessage
    from urllib.parse import quote as encode
    c=module('log_smtp','services/mrjam-courriel/courriel.py')
    smtp=c.verifier_smtp(c.lire_prive('/var/lib/mrjam-identite/proton-smtp.json'))
    message=EmailMessage();message['From']=smtp['from_address'];message['To']=plan['mail']
    message['Subject']='MrJ.am — créez votre compte Log et retrouvez Vision'
    message['Message-ID']='<log-'+d.name+'@mrj.am>'
    message.set_content('Votre nouveau compte commun est prêt. Vos données Vision restent rattachées à leur propriétaire historique.\n\n'
      'Choisissez votre phrase de passe et un TOTP, ou une passkey :\n'
      'https://log.mrj.am/ui/reset?token='+encode(plan['intent'])+'\n\n'
      'Ce lien personnel expire après 24 heures. Ne le transférez pas. Le compte administrateur exige le second facteur. '
      'Les espaces et Unicode sont acceptés ; la phrase de passe peut atteindre 128 caractères. '
      'Votre adresse sert à la connexion et à la récupération ; le pseudo est facultatif et affiche cette adresse par défaut.\n\n'
      'Après enregistrement, ouvrez https://vision.mrj.am/auth/connexion. Vos données sont conservées. '
      'Le client MCP/LLM devra être autorisé à nouveau.\n')
    ecrire(marque,{'format':1,'envoi_engage':True,'accepte_par_relais':False,'repetition_automatique':False})
    c.transmettre(smtp,message)
    preuve={'format':1,'accepte_par_relais':True,'presence_en_boite':'non_observable_par_agent',
            'enrolement_personnel':'a_effectuer','date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    ecrire(marque,preuve);return preuve

def activer(d,p,cert):
    global PHASE
    exiger(not (d/'activation-log-privee.json').exists(),'Bascule déjà engagée : constater/reprendre, ne pas répéter')
    r=json.loads((d/'restauration.json').read_text())
    exiger(r['empreintes_semantiques_identiques'] and r['retour_applicatif_qualifie'] and
           time.time()-(d/'restauration.json').stat().st_mtime<900,'Sauvegarde/restauration absente ou périmée')
    plan=amorcer(d,p,cert)
    PHASE='retour-independant'
    commande='python3 -B '+str(ROOT/'scripts/log-activer.py')+' retour '+d.name
    stage.commande(['systemd-run','--unit=mrjam-log-retour-'+d.name[:12],'--on-active=10min',
       '/run/current-system/sw/bin/nix-shell','-I','nixpkgs='+stage.NIXPKGS,'-p','python3','--run',commande],d)
    try:
        PHASE='retrait-anciennes-identites'
        stage.commande(['systemctl','stop','mrjam-metier','mrj-auth'],d)
        # Les écritures réalisées pendant la préparation sont préservées : la
        # référence de bascule est prise après quiescence, pas avant celles-ci.
        plan['donnees']=donnees();ecrire(d/'activation-log-privee.json',plan)
        # L'API administrative ne déclenche pas l'action interactive FermerCompte.
        # L'ancien IdP est sauvegardé séparément pour le retour de son identité.
        api=ancien_operateur();personne=inventorier_ancien(api)
        exiger(personne['id']==plan['ancien_idp'] and personne['email']==plan['mail'],'Compte IdP concurrent')
        plan['suppression_ancienne_engagee']=True;ecrire(d/'activation-log-privee.json',plan)
        code,_,_=api('/admin/realms/mrjam/users/'+plan['ancien_idp'],method='DELETE')
        exiger(code==204,'Retrait de l’identité IdP non constaté')
        plan['ancienne_identite_retiree']=True;ecrire(d/'activation-log-privee.json',plan)
        old=Path('/var/lib/vision/auth/htpasswd'); old.write_bytes(b'')
        PHASE='rattachement-et-activation'
        seed_log(d,plan)
        plan['rattachement_engage']=True;ecrire(d/'activation-log-privee.json',plan)
        rattacher(plan);plan['rattache']=True;ecrire(d/'activation-log-privee.json',plan)
        changer=module('log_config','scripts/monolithe-activer.py')
        changer.changer_configuration(p['configurations']['candidat'])
        stage.commande([Path(p['candidat'])/'bin/switch-to-configuration','test'],d)
        plan['phase']='qualification-active';ecrire(d/'activation-log-privee.json',plan)
        mesures=sonder(d,p,cert,plan)
        stage.commande(['systemctl','restart','mrjam-metier'],d)
        mesures=sonder(d,p,cert,plan)
        PHASE='enregistrement'
        stage.commande(['nix-env','--profile','/nix/var/nix/profiles/system','--set',p['candidat']],d)
        preuve_mail=envoyer(d,p,cert,plan)
        stage.commande(['systemctl','stop','mrjam-log-retour-'+d.name[:12]+'.timer'],d)
        plan['phase']='invitation-envoyee';ecrire(d/'activation-log-privee.json',plan)
        preuve=dict(format=1,revision=d.name,generation=p['candidat'],artefact_sha256=cert['qualification']['artefact_sha256'],
          kanidm_actif=True,keycloak_actif=False,mrj_auth_python_actif=False,proprietaire_metier_preserve=True,
          rattachement_explicite=True,anciennes_identites_retirees=True,donnees_preservees=True,
          redemarrage_verifie=True,restauration_native_isolee=True,mail=preuve_mail,services=mesures,
          etape2_complete=False,qualification_personnelle='en attente',
          limites=['Fermetures communes définitives IdP à terminer ; admission native conservée, secret borné90jours à renouveler par exploitation.',
                   'Préférences individuelles et panneau commun complet restent à qualifier ; rôle propriétaire limité à sept jours.',
                   'Connexion et autorisation MCP personnelles restent à effectuer.'])
        ecrire(d/'qualification-log-production.json',preuve);print(json.dumps(preuve,ensure_ascii=False))
    except Exception:
        retour(d,p,cert)
        raise

def retour(d,p,cert):
    global PHASE
    PHASE='retour'
    f=d/'activation-log-privee.json'
    if not f.exists(): return
    plan=json.loads(f.read_text())
    if (d/'retour-log.json').exists(): return
    stage.commande(['systemctl','stop','mrjam-metier','kanidm','keycloak'],d)
    if plan.get('rattachement_engage'):
        retablir_rattachement(plan)
    if plan.get('suppression_ancienne_engagee'):
        dump=dechiffrer(d,cert,'identite-retour.dump.age')
        subprocess.run(['runuser','-u','postgres','--','pg_restore','--clean','--if-exists','--exit-on-error',
                        '--dbname=mrjam_identite'],input=dump,capture_output=True,check=True,timeout=120)
    Path('/var/lib/vision/auth/htpasswd').write_bytes(dechiffrer(d,cert,'vision-ancienne-auth.age'))
    changer=module('log_config_retour','scripts/monolithe-activer.py')
    changer.changer_configuration(p['avant']['configuration_lien'] or p['avant']['configuration_cible'])
    stage.commande([Path(p['avant']['generation'])/'bin/switch-to-configuration','test'],d)
    stage.commande(['nix-env','--profile','/nix/var/nix/profiles/system','--set',p['avant']['generation']],d)
    stage.commande(['systemctl','start','mrjam-metier','keycloak','mrj-auth'],d)
    exiger(donnees()==plan['donnees'],'Données différentes après retour')
    ecrire(d/'retour-log.json',{'retour_code_identite':True,'restauration_base_metier':False,'donnees_preservees':True})
    subprocess.run(['systemctl','stop','mrjam-log-retour-'+d.name[:12]+'.timer'],capture_output=True)

if __name__=='__main__':
    try:
        exiger(os.geteuid()==0 and len(sys.argv)==3 and re.fullmatch('[a-f0-9]{40}',sys.argv[2]),'Opérateur/révision refusés')
        os.umask(0o077);d=Path('/root/mrjam-assemblages')/sys.argv[2]
        p=json.loads((d/'preparation-log.json').read_text());cert=stage.verifier_bundle(d/'payload')
        with open('/root/mrjam-log.lock','a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if sys.argv[1]=='activer': activer(d,p,cert)
            elif sys.argv[1]=='retour': retour(d,p,cert)
            elif sys.argv[1]=='courriel':
                plan=json.loads((d/'activation-log-privee.json').read_text())
                sonder(d,p,cert,plan);print(json.dumps(envoyer(d,p,cert,plan)))
            else: raise ValueError('Opération fermée inconnue')
    except Exception as e:
        if len(sys.argv)==3 and re.fullmatch('[a-f0-9]{40}',sys.argv[2]):
            d=Path('/root/mrjam-assemblages')/sys.argv[2]
            if d.is_dir(): (d/'erreur-log-operation-privee.log').write_text(traceback.format_exc())
        print(json.dumps({'operation_log':'refusee','phase':PHASE,'exception':type(e).__name__,
                          'diagnostic':'privé, aucun secret affiché'}),file=sys.stderr);sys.exit(1)
