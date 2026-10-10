"""Essai réservé : transfert courant, retour local indépendant, contrôles puis boot.

Aucun paramètre métier, secret, admission tierce ou restauration de vieux contenu.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import argparse
import secrets
import shlex

ROOT=Path(__file__).resolve().parents[1]
REPRISE='9ef9b074057ee9eac15a6f5cd0a0dc467d4fc80d'
VISION='a9c51acac81510d7dc896f5daf4e6fb28a36b979'


def exiger(valeur):
    if not valeur:raise ValueError('Essai Vision refusé')


def charger(nom,fichier):
    s=importlib.util.spec_from_file_location(nom,ROOT/'scripts'/fichier)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def verifier_preparation(r,revision):
    exiger(type(r.get('version')) is int and r['version']==1 and r.get('infrastructure')==revision and
        r.get('vision')==VISION and r.get('style')=='96fa28ac564b9492768837d4087608e83acc721b')
    exiger(all(r.get(k) is True for k in ('restauration_vision_reelle','restauration_identite_reelle',
        'migrations_isolees_sans_perte','association_et_admin_isoles','retour_acl_rejoue',
        'generation_complete_construite','configuration_nginx_native','dry_activate_qualifie',
        'interface_exacte','nouvelle_cle_vision_identite','cle_personnelle_verifiee','copie_exterieure_verifiee',
        'entree_persistante_reproduite','timer_independant_repete')))
    exiger(all(r.get(k) is False for k in ('production_modifiee','donnees_production_modifiees',
        'generation_active_modifiee','retour_autonome_arme','activation','inscriptions')) and
        type(r.get('fichiers_interface')) is int and r['fichiers_interface']==22)


def verifier_finalisation(d):
    exiger((d/'commence').is_file() and (d/'teste').is_file())
    exiger(not any((d/n).exists() for n in
        ('echec','retour-commence','retour-termine','enregistre')))


def installer_prive(p,contenu,mode=0o600):
    """Créer exclusivement dans des parents root réels, sans écraser de fichier."""
    for parent in [*reversed(p.parent.parents),p.parent]:
        if parent==Path('/'):continue
        if not parent.exists() and not parent.is_symlink():parent.mkdir(mode=0o755)
        s=parent.lstat()
        exiger(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as fichier:
            fichier.write(contenu);fichier.flush();os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def generateur_essai(d,outils,unite,volatile):
    """Le timer arme l'essai courant ; seul un nouveau boot ajoute le want.

    NixOS redémarre les cibles actives pendant test. /run disparaît au reboot.
    L'unité de retour qualifiée reste publiée dans les deux situations.
    """
    exiger(re.fullmatch(r'vision-essai-retour-[a-f0-9]{12}',unite))
    q=shlex.quote
    return f'''#!{outils}/bash
set -euo pipefail
{q(str(d/'reprise-generateur.sh'))} "$@"
if test -e {q(str(volatile))}; then
  {q(str(outils/'rm'))} -f "$1/multi-user.target.wants/{unite}.service"
fi
'''


def preparer_parent_backend(parent,groupe):
    # Le umask privé0077 retire g+rx même à mkdir(mode=0750).
    # Fixer les droits effectifs avant toute copie ou bascule du lien.
    if not parent.exists() and not parent.is_symlink():parent.mkdir(mode=0o750)
    info=parent.lstat()
    exiger(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022)
    os.chown(parent,0,groupe);parent.chmod(0o750)


class Essai:
    def __init__(self,revision):
        exiger(os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',revision))
        os.umask(0o077)
        self.revision=revision;self.d=Path('/root/vision-essais')/revision
        exiger(ROOT==self.d/'source')
        self.prive=charger('prive_essai','identite-preparer.py')
        self.construction=charger('construction_essai','vision-identite-construire.py')
        for p in (self.d.parent,self.d,ROOT):self.construction.dossier_prive(p)
        self.prepare=Path('/root/vision-bascule-preparations')/revision
        self.construction.dossier_prive(self.prepare)
        verifier_preparation(self.lire('essai-preparation.json',self.prepare),revision)
        self.evaluation=self.lire('evaluation-essai.json',self.prepare)
        self.ancien=self.evaluation['systeme_actif'];self.nouveau=self.evaluation['systeme_candidat']
        for n in ('systeme_actif','systeme_candidat','postgres_paquet','backend_paquet','interface_store'):
            self.construction.store(self.evaluation[n])
        self.outils=Path(self.ancien)/'sw/bin'
        self.qual=charger('qualification_essai','vision-essai-qualification.py')
        self.reprise=charger('reprise_essai','vision-essai-reprise.py')
        self.qual.verifier_recuperation(json.loads((ROOT/'operations/vision-recuperation-resultat.json').read_text()),
            json.loads((ROOT/'operations/vision-recuperation-confirmation.json').read_text()))
        recu=json.loads((ROOT/'operations/vision-reprise-qualification-reelle.json').read_text())
        exiger(recu['infrastructure']==REPRISE and recu['execution']==38068969303 and recu['job']==114262328234)
        native=self.lire('qualification.json',Path('/root/vision-retour-qualifications')/REPRISE)
        exiger(all(recu.get(k)==v for k,v in native.items()) and all(native.get(k) is True for k in
            ('conditions_systemd_natives','reprise_generateur_reconstruit','reprise_ordonnancement_systemd_natif',
             'reprise_clients_fermes_avant_demarrage','reprise_marques_terminales_respectees','reprise_executee_en_fixture')))
        self.candidat=json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
        self.acl=charger('acl_essai','vision-acl.py')
        self.association=charger('association_essai','vision-bascule-principaux.py')
        self.preparateur=charger('preparateur_essai','vision-bascule-preparer.py')
        q=json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
        self.resume=self.lire('evaluation-privee.json',Path('/root/vision-identite-amorcage-operations')/q['infrastructure'])
        self.pg=Path(self.resume['postgres_paquet'])/'bin'
        self.runuser=Path(self.resume['runuser_paquet'])/'bin/runuser'
        self.age=Path(self.resume['age_paquet'])/'bin/age'
        self.worker='vision-essai-'+revision[:12]+'.service'
        self.unite_retour='vision-essai-retour-'+revision[:12]
        self.fd=os.open(self.d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.generateur=Path('/usr/local/lib/systemd/system-generators')/('vision-essai-'+revision[:12])
        self.timer=Path('/run/systemd/system')/(self.unite_retour+'.timer')
        self.volatile=Path('/run')/('vision-essai-'+revision[:12]+'-actif')

    def lire(self,nom,d=None):
        d=d or self.d;self.construction.dossier_prive(d)
        fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:return json.loads(self.prive.lire(fd,nom))
        finally:os.close(fd)

    def ecrire(self,nom,texte):self.prive.ecrire(self.fd,nom,texte)
    def sauver(self,nom,valeur):self.ecrire(nom,json.dumps(valeur))
    def marquer(self,nom):
        exiger(not (self.d/nom).exists())
        temporaire='marque-'+secrets.token_hex(16)
        self.ecrire(temporaire,'1\n')
        os.replace(temporaire,nom,src_dir_fd=self.fd,dst_dir_fd=self.fd)
        os.fsync(self.fd)

    def commande(self,*a,entree=None,env=None,timeout=120):
        propre={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        if env:propre.update(env)
        r=subprocess.run([str(x) for x in a],input=entree,env=propre,
            capture_output=True,timeout=timeout)
        if r.returncode:
            log=os.open('diagnostic-prive.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,
                0o600,dir_fd=self.fd)
            try:
                st=os.fstat(log);exiger(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and
                    stat.S_IMODE(st.st_mode)==0o600)
                if st.st_size<1048576:os.write(log,(r.stderr+r.stdout)[:1048576-st.st_size]);os.fsync(log)
            finally:os.close(log)
            exiger(False)
        return r.stdout.decode().strip()

    def sql(self,base,q,socket='/run/postgresql'):
        return self.commande(self.runuser,'-u','postgres','--',self.pg/'psql','-XAtq',
            '-v','ON_ERROR_STOP=1','-h',socket,'-U','postgres','-d',base,'-f','-',
            entree=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n"+q).encode())

    def arreter(self,unite):
        charge=self.commande(self.outils/'systemctl','show',unite,'--property=LoadState','--value')
        if charge=='not-found':return
        self.commande(self.outils/'systemctl','stop',unite)
        exiger(self.commande(self.outils/'systemctl','show',unite,'--property=ActiveState','--value') in ('inactive','failed'))

    def verrou_deploiement(self):
        fd=os.open('/srv/vision/deploy.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        info=os.fstat(fd)
        exiger(stat.S_ISREG(info.st_mode) and info.st_nlink==1)
        fcntl.flock(fd,fcntl.LOCK_EX)
        return fd

    def empreintes(self,base,tables,socket='/run/postgresql'):
        return self.preparateur.empreintes(lambda q:self.sql(base,q,socket),tables,self.acl)

    def dump(self,base,nom,socket):
        destination=self.d/nom
        fd=self.prive.ouvrir_prive(self.fd,nom,os.O_WRONLY|os.O_CREAT|os.O_EXCL,maximum=512*1024**2)
        try:
            r=subprocess.run([str(self.runuser),'-u','postgres','--',str(self.pg/'pg_dump'),'-Fc',
                '-h',socket,'-U','postgres',base],stdout=fd,stderr=subprocess.PIPE,
                env={k:v for k,v in os.environ.items() if not k.startswith('PG')},timeout=120)
            exiger(r.returncode==0 and os.fstat(fd).st_size<512*1024**2)
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(self.fd)
        self.commande(self.age,'-r',self.qual.RECIPIENT,'-o',str(destination)+'.age',destination)
        return destination

    def snapshots(self):
        # Les trois écrivains historiques sont déjà arrêtés et les nouveaux
        # services n'ont pas encore été activés ; aucun dump n'est affiché.
        legacy=charger('legacy_essai','vision-proprietaire.py')
        import grp
        auth=legacy.identifiants_auth(Path('/var/lib/vision/auth/htpasswd'),0,grp.getgrnam('vision-auth').gr_gid)
        q=lambda t:self.sql('vision',t)
        historique=legacy.inspecter(q,auth);releve=self.acl.relever(q)
        exiger(releve['proprietaires']==[historique['utilisateur_historique']])
        state=Path('/var/lib/mrjam-proprietaire')
        public=json.loads((ROOT/'operations/vision-proprietaire-observation.json').read_text())
        compte=self.lire('compte.json',state)
        noms=[n for n in os.listdir(state) if re.fullmatch(r'connexion-[0-9]{1,12}\.json',n)]
        identite=self.association.verifier_preuve(public,compte,{n:self.lire(n,state) for n in noms})
        tables=json.loads(q("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' AND tablename<>'vision_schema_migrations'"))
        exiger(1<=len(tables)<=100 and all(re.fullmatch('[a-z0-9_]{1,70}',n) for n in tables))
        avant=self.empreintes('vision',tables)
        vieux='/run/mrjam-amorcage-postgresql'
        tables_idp=json.loads(self.sql('mrjam_identite',"SELECT json_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='public';",vieux))
        exiger(1<=len(tables_idp)<=300 and all(re.fullmatch('[a-z0-9_]{1,70}',n) for n in tables_idp))
        idp=self.empreintes('mrjam_identite',tables_idp,vieux)
        self.sauver('acl-avant.json',releve);self.ecrire('retour-acl.sql',self.acl.retour(releve))
        self.sauver('donnees-avant.json',dict(tables=tables,empreintes=avant))
        self.sauver('identite-avant.json',dict(tables=tables_idp,empreintes=idp))
        self.sauver('association-privee.json',dict(identite=identite,historique=historique))
        # Cette comparaison est réutilisée par le retour sans Python.
        verification="SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n"
        for t in tables_idp:
            verification+="SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),' ' ORDER BY md5(to_jsonb(t)::text)),'')) FROM public."+self.acl.identifiant(t)+' t;\n'
        self.ecrire('identite-empreintes.sql',verification)
        vision=self.dump('vision','vision-avant.dump','/run/postgresql')
        transfert=self.dump('mrjam_identite','identite-avant.dump',vieux)
        vision.unlink();os.fsync(self.fd)
        return transfert

    def migrer(self,transfert):
        donnees=self.lire('donnees-avant.json');idp=self.lire('identite-avant.json')
        association=self.lire('association-privee.json')
        source=self.prepare/'vision'
        self.marquer('sql-engage')
        self.sql('postgres',"CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT; CREATE DATABASE mrjam_identite OWNER keycloak;")
        self.sql('postgres','REVOKE ALL ON DATABASE mrjam_identite FROM PUBLIC; GRANT CONNECT ON DATABASE mrjam_identite TO keycloak;')
        self.commande(self.runuser,'-u','postgres','--',self.pg/'pg_restore','--single-transaction',
            '--exit-on-error','--no-owner','--no-privileges','--role=keycloak','-h','/run/postgresql',
            '-U','postgres','-d','mrjam_identite',entree=transfert.read_bytes())
        exiger(self.empreintes('mrjam_identite',idp['tables'])==idp['empreintes'])
        # Aucun Keycloak nouveau ne peut écrire avant cette preuve durable.
        self.marquer('identite-migree')
        transfert.unlink();os.fsync(self.fd)
        # Lire le SQL root privé et l'envoyer à psql sous le compte postgres ;
        # ni script déployeur ni connexion peer root→postgres.
        migrations=['SELECT pg_advisory_lock(718,15);']
        for numero in range(19,26):
            fichiers=list((source/'migrations').glob(f'{numero:03d}_*.sql'))
            exiger(len(fichiers)==1 and fichiers[0].is_file() and not fichiers[0].is_symlink())
            migrations.append(fichiers[0].read_text())
        self.sql('vision','\n'.join(migrations))
        self.sql('vision',(source/'scripts/roles.sql').read_text())
        self.sql('vision',self.association.association_sql(association['identite'],association['historique'],self.acl.litteral))
        exiger(self.empreintes('vision',donnees['tables'])==donnees['empreintes'])
        self.verifier_comptes()

    def verifier_comptes(self):
        association=self.lire('association-privee.json');i=association['identite'];h=association['historique']
        obtenu=json.loads(self.sql('vision',"SELECT json_build_object('comptes',(SELECT count(*) FROM vision_gestion.comptes),'administrateurs',(SELECT count(*) FROM vision_gestion.comptes WHERE administrateur),'identites',(SELECT count(*) FROM vision_gestion.identites),'issuer',emetteur,'sujet',sujet,'utilisateur',utilisateur,'inscriptions',(SELECT inscriptions_ouvertes FROM vision_gestion.configuration)) FROM vision_gestion.identites;"))
        exiger(obtenu==dict(comptes=1,administrateurs=1,identites=1,issuer=i['issuer'],sujet=i['sujet'],utilisateur=h['utilisateur_historique'],inscriptions=False))
        exiger(self.sql('vision',"SELECT count(*)=0 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind IN ('r','p','v','m') AND has_table_privilege('vision_administration',c.oid,'SELECT,INSERT,UPDATE,DELETE');")=='t')
        exiger(self.sql('vision',"SELECT count(*)=0 FROM pg_roles WHERE rolname IN ('vision','vision_administration','vision_identite','vision_cycle','vision_admission','vision_fermeture','keycloak') AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);")=='t')

    def verifier_backend(self):
        plan=self.lire('plan.json');nouveau=Path(plan['backend'])
        attendu=self.lire('backend-empreintes.json')
        exiger(Path('/srv/vision/current').resolve()==nouveau and not nouveau.is_symlink())
        exiger(set(attendu)=={str(p.relative_to(nouveau)) for p in nouveau.rglob('*') if p.is_file()})
        for n,h in attendu.items():
            p=nouveau/n;s=p.lstat()
            exiger(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and
                hashlib.sha256(p.read_bytes()).hexdigest()==h)

    def verifier_local(self,enregistre=False):
        exiger(Path('/run/current-system').resolve()==Path(self.nouveau))
        exiger(Path('/nix/var/nix/profiles/system').resolve()==Path(self.nouveau if enregistre else self.ancien))
        self.commande(self.outils/'systemctl','is-active','sshd','nginx','postgresql','vision','matheval','mrj-auth',
            'keycloak','vision-gestion','vision-cycle','mrjam-admission','mrjam-fermeture','mrjam-courriel')
        exiger(self.sql('postgres',"SELECT current_setting('listen_addresses')='' AND current_setting('unix_socket_directories')='/run/postgresql' AND current_setting('data_directory')='/var/lib/postgresql/17' AND current_setting('server_version_num')::int/10000=17;")=='t')
        environment=self.commande(self.outils/'systemctl','show','mrj-auth.service','--property=Environment','--value')
        exiger('MRJ_AUTH_MODE=oidc' in environment and 'MRJ_OIDC_ISSUER=https://log.mrj.am/realms/mrjam' in environment)
        self.verifier_comptes();self.verifier_backend()
        exiger(hashlib.sha256((Path(self.evaluation['interface_store'])/'manifest.json').read_bytes()).hexdigest()==self.qual.MANIFESTE)
        exiger(self.sql('mrjam_identite',"SELECT count(*)=1 AND bool_and(enabled) FROM user_entity WHERE realm_id=(SELECT id FROM realm WHERE name='mrjam') AND service_account_client_link IS NULL;")=='t')
        sujet=self.acl.litteral(self.lire('association-privee.json')['identite']['sujet'])
        exiger(self.sql('mrjam_identite',"SELECT count(*)=2 AND count(DISTINCT type)=2 FROM credential WHERE user_id="+sujet+" AND type IN ('password','otp');")=='t')

    def worker_execute(self):
        verrou=self.verrou_deploiement()
        try:
            exiger((self.d/'commence').is_file() and not any((self.d/n).exists() for n in ('enregistre','retour-commence','retour-termine','teste')))
            self.verifier_socle()
            self.commande(self.outils/'systemctl','is-active',self.unite_retour+'.timer')
            for u in ('vision.service','mrj-auth.service','mrjam-amorcage-identite.service'):self.arreter(u)
            transfert=self.snapshots();self.migrer(transfert)
            plan=self.lire('plan.json');temp=Path('/srv/vision/vision-essai-'+self.revision[:12])
            exiger(not temp.exists() and not temp.is_symlink());temp.symlink_to(plan['backend']);os.replace(temp,'/srv/vision/current')
            self.commande(self.outils/'sync','-f','/srv/vision')
            self.commande(Path(self.nouveau)/'bin/switch-to-configuration','test',timeout=360)
            self.verifier_local()
            self.commande(self.outils/'systemctl','start','mrjam-sauvegarde.service',timeout=120)
            exiger(self.commande(self.outils/'systemctl','show','mrjam-sauvegarde.service','--property=Result','--value')=='success')
            for prefixe in ('vision-','mrjam_identite-','sessions-'):
                copies=list(Path('/var/backup/mrjam').glob(prefixe+'*.age'))
                exiger(any(p.is_file() and not p.is_symlink() and p.stat().st_uid==0 and
                    stat.S_IMODE(p.stat().st_mode)==0o600 and p.stat().st_size>100 and
                    p.stat().st_mtime>=(self.d/'commence').stat().st_mtime for p in copies))
            self.marquer('teste')
            print(json.dumps(dict(controles_locaux=True,retour_arme=True,inscriptions=False)),flush=True)
            # Garder le verrou applicatif pendant les contrôles HTTP indépendants.
            limite=time.monotonic()+420
            while time.monotonic()<limite:
                if (self.d/'enregistre').exists():return
                if (self.d/'retour-commence').exists():exiger(False)
                time.sleep(2)
            exiger(False)
        except Exception:
            if not (self.d/'echec').exists():self.marquer('echec')
            raise
        finally:os.close(verrou)

    def verifier_socle(self):
        exiger(Path('/run/current-system').resolve()==Path(self.ancien) and
            Path('/nix/var/nix/profiles/system').resolve()==Path(self.ancien))
        exiger(Path('/srv/vision/current').resolve()==Path(self.candidat['audit']['vision']))
        original=Path('/root/vision-proprietaire-operations')/self.association.OBSERVATION/'source/scripts'
        fd=os.open(original,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:exiger(hashlib.sha256(self.prive.lire(fd,'vision-proprietaire-enroler.py',65536).encode()).hexdigest()==self.preparateur.OBSERVER_HASH)
        finally:os.close(fd)
        observer=charger('observateur_essai',original/'vision-proprietaire-enroler.py')
        observer.main(self.association.OBSERVATION,observer=True,activation_seule=True)

    def copier_backend(self):
        src=Path(self.evaluation['backend_paquet'])/'app'
        exiger((src/'RELEASE').read_text().strip()==VISION)
        parent=Path('/srv/vision-essais')
        import grp
        groupe=grp.getgrnam('vision').gr_gid
        preparer_parent_backend(parent,groupe)
        nouveau=parent/(VISION+'-root-'+self.revision[:12])
        exiger(not nouveau.exists() and not nouveau.is_symlink())
        paths=list(src.rglob('*'));exiger(len(paths)<2048 and all(not p.is_symlink() for p in paths))
        exiger(sum(p.stat().st_size for p in paths if p.is_file())<512*1024**2)
        shutil.copytree(src,nouveau)
        empreintes={}
        for p in [nouveau,*nouveau.rglob('*')]:
            os.chown(p,0,groupe)
            if p.is_dir():p.chmod(0o750)
            else:
                exiger(p.is_file())
                relatif=str(p.relative_to(nouveau));origine=src/relatif
                h=hashlib.sha256(p.read_bytes()).hexdigest()
                exiger(h==hashlib.sha256(origine.read_bytes()).hexdigest())
                empreintes[relatif]=h;p.chmod(0o550 if origine.stat().st_mode&0o111 else 0o440)
        self.sauver('backend-empreintes.json',empreintes)
        return nouveau

    def preparer(self):
        exiger(not (self.d/'plan.json').exists() and not (self.d/'commence').exists())
        self.verifier_socle()
        exiger(self.sql('vision','SELECT count(*)=18 AND max(version)=18 FROM vision_schema_migrations;')=='t')
        exiger(self.sql('postgres',"SELECT count(*)=0 FROM pg_database WHERE datname='mrjam_identite';")=='t')
        exiger(self.sql('postgres',"SELECT count(*)=0 FROM pg_roles WHERE rolname='keycloak';")=='t')
        recherche=self.commande(self.outils/'systemd-path','systemd-search-system-generator')
        exiger('/usr/local/lib/systemd/system-generators' in recherche.split(':'))
        configuration=Path('/etc/nixos/configuration.nix')
        exiger(configuration.is_symlink() and re.fullmatch(r'/root/vision-identite-amorcage-essais/[a-f0-9]{40}/entree.nix',str(configuration.resolve())))
        self.commande(self.outils/'cp','-a','--no-dereference',configuration,self.d/'configuration-avant.nix')
        (self.d/'backend-avant').symlink_to(Path('/srv/vision/current').resolve())
        fd=os.open(self.prepare,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:self.ecrire('entree.nix',self.prive.lire(fd,'entree.nix'))
        finally:os.close(fd)
        retour=self.qual.script_retour(self.d,self.ancien,self.outils,self.pg.parent,self.runuser,self.worker)
        self.ecrire('retour.sh',retour);(self.d/'retour.sh').chmod(0o700)
        self.commande(self.outils/'bash','-n',self.d/'retour.sh')
        for n,t in self.reprise.fichiers(self.d,self.outils,self.unite_retour).items():
            self.ecrire(n,t)
            if n.endswith('.sh'):
                (self.d/n).chmod(0o700);self.commande(self.outils/'bash','-n',self.d/n)
        # Le backend est copié sous le verrou sans changer le lien actif.
        self.ecrire('generateur-essai.sh',generateur_essai(self.d,self.outils,self.unite_retour,self.volatile))
        (self.d/'generateur-essai.sh').chmod(0o700)
        self.commande(self.outils/'bash','-n',self.d/'generateur-essai.sh')
        lock=os.open('/srv/vision/deploy.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX);nouveau=self.copier_backend()
        finally:os.close(lock)
        for nom,paquet in (('ancien',self.ancien),('candidat',self.nouveau),('python',str(Path(sys.executable).resolve().parents[1]))):
            racine=Path('/nix/var/nix/gcroots')/('vision-essai-'+self.revision[:12]+'-'+nom)
            exiger(not racine.exists() and not racine.is_symlink());racine.symlink_to(paquet)
        self.sauver('plan.json',dict(version=1,infrastructure=self.revision,ancien=self.ancien,
            nouveau=self.nouveau,backend=str(nouveau),source_configuration=str(configuration.resolve()),
            configuration_sha256=hashlib.sha256(configuration.read_bytes()).hexdigest(),
            retour_arme=False,activation=False,inscriptions=False))
        print(json.dumps(dict(essai_prepare=True,retour_arme=False,activation=False,inscriptions=False)),flush=True)

    def lancer(self):
        self.verifier_socle()
        exiger((self.d/'plan.json').is_file() and not (self.d/'commence').exists())
        # Ces quatre fichiers doivent rester les mêmes que lors de la répétition
        # réelle sur le VPS ; le nouvel opérateur ne modifie pas le retour.
        qualification=Path('/root/vision-retour-qualifications')/REPRISE/'source/scripts'
        for nom in ('vision-essai-retour.sh','vision-essai-reprise.py','vision-acl.py','vision-bascule-principaux.py'):
            exiger(hashlib.sha256((ROOT/'scripts'/nom).read_bytes()).digest()==
                hashlib.sha256((qualification/nom).read_bytes()).digest())
        # /etc/systemd/system-generators appartient au store Nix en lecture seule.
        installer_prive(self.volatile,b'1\n')
        installer_prive(self.generateur,(self.d/'generateur-essai.sh').read_bytes(),0o700)
        installer_prive(self.timer,(self.d/'reprise.timer').read_bytes())
        self.marquer('commence')
        self.commande(self.outils/'systemctl','daemon-reload')
        fragment=self.commande(self.outils/'systemctl','show',self.unite_retour+'.service','--property=FragmentPath','--value')
        exiger(fragment.startswith('/run/systemd/generator/') and fragment.endswith('/'+self.unite_retour+'.service'))
        self.commande(self.outils/'systemctl','start',self.unite_retour+'.timer')
        self.commande(self.outils/'systemctl','is-active',self.unite_retour+'.timer')
        self.commande(self.outils/'systemd-run','--unit='+self.worker,'--property=Type=exec',
            '--property=RuntimeMaxSec=10min','--property=TimeoutStopSec=45s',
            '--property=KillMode=control-group','--property=UMask=0077',
            '--property=StandardOutput=null','--property=StandardError=null',
            str(Path(sys.executable).resolve()),ROOT/'scripts/vision-essai-activer.py',self.revision,'worker')
        print(json.dumps(dict(retour_arme=True,essai_lance=True,inscriptions=False)),flush=True)

    def attendre(self):
        limite=time.monotonic()+480
        while time.monotonic()<limite:
            exiger(not any((self.d/n).exists() for n in ('echec','retour-commence','retour-termine','enregistre')))
            if (self.d/'teste').exists():
                self.commande(self.outils/'systemctl','is-active',self.worker,self.unite_retour+'.timer')
                self.verifier_local()
                print(json.dumps(dict(essai_actif=True,controles_locaux=True,retour_arme=True,inscriptions=False)),flush=True)
                return
            time.sleep(2)
        exiger(False)

    def finaliser(self):
        lock=os.open(self.d/'finalisation.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX)
            verifier_finalisation(self.d)
            self.commande(self.outils/'systemctl','is-active',self.worker,self.unite_retour+'.timer')
            self.verifier_local()
            plan=self.lire('plan.json');configuration=Path('/etc/nixos/configuration.nix')
            exiger(configuration.is_symlink() and str(configuration.resolve())==plan['source_configuration'] and
                hashlib.sha256(configuration.read_bytes()).hexdigest()==plan['configuration_sha256'])
            temporaire=configuration.parent/('vision-essai-'+self.revision[:12]+'.nix')
            exiger(not temporaire.exists() and not temporaire.is_symlink())
            temporaire.symlink_to(self.d/'entree.nix');os.replace(temporaire,configuration)
            self.commande(self.outils/'sync','-f',configuration.parent)
            self.commande(self.outils/'nix-env','-p','/nix/var/nix/profiles/system','--set',self.nouveau)
            self.commande(Path(self.nouveau)/'bin/switch-to-configuration','boot',timeout=120)
            self.verifier_local(enregistre=True)
            self.sauver('activation.json',dict(version=1,infrastructure=self.revision,vision=VISION,
                activation=True,configuration_persistante=True,donnees_historiques_conservees=True,
                identite_courante_transferee=True,administrateur_sans_contenu=True,
                sauvegarde_commune_executee=True,inscriptions=False,
                connexion_humaine_vision_verifiee=False))
            self.marquer('enregistre')
        finally:os.close(lock)
        self.commande(self.outils/'systemctl','stop',self.unite_retour+'.timer')
        for p in (self.generateur,self.timer,self.volatile):
            if p.exists():
                exiger(not p.is_symlink() and p.stat().st_uid==0);p.unlink()
                self.commande(self.outils/'sync','-f',p.parent)
        self.commande(self.outils/'systemctl','daemon-reload')
        print(json.dumps(self.lire('activation.json')),flush=True)

    def retourner(self):
        if not (self.d/'commence').exists():
            print(json.dumps(dict(essai_non_commence=True,activation=False)),flush=True);return
        if (self.d/'enregistre').exists():
            print(json.dumps(dict(activation=True,retour_neutralise=True)),flush=True);return
        self.commande(self.outils/'systemctl','daemon-reload')
        self.commande(self.outils/'systemctl','reset-failed',self.unite_retour+'.service')
        self.commande(self.outils/'systemctl','start',self.unite_retour+'.service')
        limite=time.monotonic()+360
        while time.monotonic()<limite:
            if (self.d/'retour-termine').exists():
                exiger(Path('/run/current-system').resolve()==Path(self.ancien) and
                    Path('/srv/vision/current').resolve()==Path(self.candidat['audit']['vision']))
                self.commande(self.outils/'systemctl','is-active','sshd','nginx','postgresql','vision','matheval','mrj-auth')
                print(json.dumps(dict(retour_effectif=True,activation=False,inscriptions=False)),flush=True);return
            time.sleep(2)
        exiger(False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('revision')
    parser.add_argument('phase',choices=('preparer','lancer','worker','attendre','finaliser','retourner'))
    a=parser.parse_args()
    try:
        essai=Essai(a.revision)
        try:getattr(essai,'worker_execute' if a.phase=='worker' else a.phase)()
        finally:os.close(essai.fd)
    except Exception:
        sys.exit('Essai Vision refusé ; diagnostic privé et retour indépendant conservés.')


if __name__=='__main__':main()
