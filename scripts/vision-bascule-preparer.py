"""Relever le socle enregistré et qualifier uniquement une association isolée."""
import argparse
import hashlib
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import select
import shutil
import signal
import stat
import subprocess
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'
DIAGNOSTIC = None
REPARATION = None
OBSERVER_HASH = '61ba89f8551a95a026293fca6ff3e79a6e5a9b6ed34c96255aa9828986ec2c2e'


def charger(nom, fichier):
    s = importlib.util.spec_from_file_location(nom, fichier)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def exiger(condition):
    if not condition: raise ValueError('Préparation réservée refusée')


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape_bascule': nom}), flush=True)


def diagnostic(contenu):
    if DIAGNOSTIC is None: return
    fd = os.open(DIAGNOSTIC, os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
    try:
        s = os.fstat(fd)
        exiger(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600)
        if s.st_size < 262144: os.write(fd, contenu[:262144-s.st_size]); os.fsync(fd)
    finally: os.close(fd)


def commande(*args, input=None, env=None, timeout=180, sortie=None):
    r = subprocess.run([str(a) for a in args], input=input, env=env,
        stdout=sortie if sortie is not None else subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if r.returncode:
        print(json.dumps(dict(commande_refusee=True,etape_bascule=ETAPE,
            code=r.returncode if -64 <= r.returncode <= 255 else None)),flush=True)
        try:
            lecteur = charger('categories_commande_bascule',ROOT/'scripts/vision-bascule-diagnostiquer.py')
            print(json.dumps(dict(categories_commande=lecteur.classer(r.stderr.decode(errors='replace'),{})['categories'])),flush=True)
        except Exception: pass
        diagnostic(r.stderr); exiger(False)
    return r.stdout.decode() if r.stdout is not None else ''


def environnement():
    return {k:v for k,v in os.environ.items() if not k.startswith('PG')}


class Transaction:
    def __init__(self, runuser, b, socket, base):
        self.runuser, self.b, self.socket, self.base = runuser, b, socket, base
    def __enter__(self):
        self.p = subprocess.Popen([str(self.runuser), '-u', 'postgres', '--', str(self.b/'psql'),
            '-XAtq', '-v', 'ON_ERROR_STOP=1', '-h', self.socket, '-U', 'postgres', '-d', self.base],
            env=environnement(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.p.stdin.write(b"SET TIME ZONE 'UTC'; SET DateStyle='ISO'; BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='5s';\n"); self.p.stdin.flush()
        return self
    def query(self, sql):
        self.p.stdin.write((sql+';\n').encode()); self.p.stdin.flush()
        exiger(bool(select.select([self.p.stdout], [], [], 20)[0]))
        ligne = self.p.stdout.readline(1048577)
        exiger(0 < len(ligne) <= 1048576 and ligne.endswith(b'\n'))
        return ligne.decode().strip()
    def __exit__(self, *_):
        try:
            if self.p.poll() is None:
                self.p.stdin.write(b'ROLLBACK;\n'); self.p.stdin.close(); self.p.wait(timeout=20)
        finally:
            if self.p.poll() is None: self.p.kill(); self.p.wait(timeout=5)
            self.p.stdout.close()


def empreintes(requete, tables, acl):
    return {t:requete("SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),' ' ORDER BY md5(to_jsonb(t)::text)),'')) FROM public."+acl.identifiant(t)+' t') for t in tables}


def preparer(revision):
    global DIAGNOSTIC, REPARATION
    exiger(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', revision))
    os.umask(0o077)
    d = Path('/root/vision-bascule-preparations')/revision
    exiger(ROOT == d/'source')
    construction = charger('construction_bascule', ROOT/'scripts/vision-identite-construire.py')
    prive = charger('prive_bascule', ROOT/'scripts/identite-preparer.py')
    association = charger('association_bascule', ROOT/'scripts/vision-bascule-principaux.py')
    legacy = charger('legacy_bascule', ROOT/'scripts/vision-proprietaire.py')
    preparation = charger('extraction_bascule', ROOT/'scripts/vision-multiutilisateur-preparer.py')
    acl = preparation.acl
    for p in (d.parent,d,ROOT): construction.dossier_prive(p)
    DIAGNOSTIC = d/'diagnostic-prive.log'
    exiger(not (d/'commence').exists() and not (d/'preparation.json').exists())
    public = json.loads((ROOT/'operations/vision-proprietaire-observation.json').read_text())
    old = Path('/root/vision-proprietaire-operations')/association.OBSERVATION/'source'
    for p in (old.parent.parent,old.parent,old,old/'scripts'): construction.dossier_prive(p)
    fd = os.open(old/'scripts', os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: exiger(hashlib.sha256(prive.lire(fd, 'vision-proprietaire-enroler.py', 65536).encode()).hexdigest() == OBSERVER_HASH)
    finally: os.close(fd)
    observateur = charger('observateur_qualifie_bascule', old/'scripts/vision-proprietaire-enroler.py')
    etape('socle_et_compte_actuels')
    observateur.main(association.OBSERVATION, observer=True, activation_seule=True)
    state = Path('/var/lib/mrjam-proprietaire'); construction.dossier_prive(state)
    fd = os.open(state, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        compte = json.loads(prive.lire(fd,'compte.json',16384))
        noms = [nom for nom in os.listdir(fd) if re.fullmatch(r'connexion-[0-9]{1,12}\.json',nom)]
        exiger(len(noms) == 1)
        identite = association.verifier_preuve(public, compte, {n:json.loads(prive.lire(fd,n,16384)) for n in noms})
    finally: os.close(fd)
    candidat = json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    activation = json.loads((ROOT/'operations/vision-identite-amorcage-activation.json').read_text())
    qualification = json.loads((ROOT/'operations/vision-identite-amorcage-qualification.json').read_text())
    prepare = Path('/root/vision-identite-amorcage-operations')/qualification['infrastructure']
    fd = os.open(prepare,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: resume = json.loads(prive.lire(fd,'evaluation-privee.json'))
    finally: os.close(fd)
    b = Path(resume['postgres_paquet'])/'bin'
    runuser = Path(resume['runuser_paquet'])/'bin/runuser'
    age = Path(resume['age_paquet'])/'bin/age'
    for p in (b.parent,runuser.parent.parent,age.parent.parent): construction.store(str(p))
    def sauver(nom,valeur):
        fd = os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: prive.ecrire(fd,nom,json.dumps(valeur))
        finally: os.close(fd)
    sauver('commence',dict(version=1))
    etape('reference_configuration')
    disponible = next(int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
    exiger(disponible >= 3*1024*1024)
    REPARATION = charger('reparation_configuration_bascule',ROOT/'scripts/vision-configuration-reparer.py')
    REPARATION.reparer(ROOT,d,activation,qualification,candidat,prive,construction,commande)
    etape('source_candidate')
    source = d/'vision'; source.mkdir(mode=0o700)
    preparation.extraire(ROOT/'vendor/vision-multiutilisateur-source.tar.gz',source,candidat['source_sha256'],candidat['vision'])
    exiger(json.loads((source/'interface/style.lock.json').read_text())['revision'] == candidat['style'])
    config = json.loads(commande('nix-instantiate','--eval','--strict','--json',ROOT/'scripts/vision-multiutilisateur-config.nix',
        '--argstr','configuration','/etc/nixos/configuration.nix','--argstr','fournisseur',candidat['audit']['fournisseur'],
        '-I','nixpkgs='+candidat['audit']['nixpkgs']))
    exiger(config['systeme'] == activation['systeme_amorcage'] and config['postgres_paquet'] == resume['postgres_paquet'] and
        config['postgres_majeure'] == '17' and config['postgres_tcp'] is False and config['postgres_ecoute'] == '' and
        config['fournisseur_source'] == candidat['audit']['fournisseur'])
    sauver('systeme-actif.json',config)
    commande('tar','--acls','--xattrs','-cpf',d/'nixos-avant.tar','-C','/etc','nixos')
    disponible = next(int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
    espace = os.statvfs('/var/lib/postgresql')
    exiger(disponible >= 3*1024*1024 and espace.f_bavail*espace.f_frsize >= 2*1024**3)
    postgres = pwd.getpwnam('postgres')
    isole = Path('/var/lib/postgresql')/('vision-bascule-'+revision[:12])
    exiger(not isole.exists()); isole.mkdir(mode=0o700); os.chown(isole,postgres.pw_uid,postgres.pw_gid)
    actif = False
    try:
        etape('snapshots_prives')
        auth = legacy.identifiants_auth(Path('/var/lib/vision/auth/htpasswd'),0,grp.getgrnam('vision-auth').gr_gid)
        with Transaction(runuser,b,'/run/postgresql','vision') as t:
            historique = legacy.inspecter(t.query,auth)
            releve = acl.relever(t.query)
            exiger(releve['proprietaires'] == [historique['utilisateur_historique']])
            sauver('historique-prive.json',historique); sauver('acl-avant.json',releve)
            tables = json.loads(t.query("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' AND tablename<>'vision_schema_migrations'"))
            avant = empreintes(t.query,tables,acl); sauver('empreintes-privees.json',avant)
            snapshot = t.query('SELECT pg_export_snapshot()'); exiger(re.fullmatch('[0-9A-F-]{1,64}',snapshot))
            with (isole/'vision.dump').open('xb') as f:
                commande(runuser,'-u','postgres','--',b/'pg_dump','-Fc','--snapshot='+snapshot,'-h','/run/postgresql','-U','postgres','vision',env=environnement(),timeout=600,sortie=f)
        with Transaction(runuser,b,'/run/mrjam-amorcage-postgresql','mrjam_identite') as t:
            tables_idp = json.loads(t.query("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public'"))
            exiger(isinstance(tables_idp,list) and 1 <= len(tables_idp) <= 300 and all(re.fullmatch('[a-z0-9_]{1,70}',n) for n in tables_idp))
            idp_avant = empreintes(t.query,tables_idp,acl); sauver('empreintes-identite-privees.json',idp_avant)
            snapshot = t.query('SELECT pg_export_snapshot()'); exiger(re.fullmatch('[0-9A-F-]{1,64}',snapshot))
            with (isole/'identite.dump').open('xb') as f:
                commande(runuser,'-u','postgres','--',b/'pg_dump','-Fc','--snapshot='+snapshot,'-h','/run/mrjam-amorcage-postgresql','-U','postgres','mrjam_identite',env=environnement(),timeout=600,sortie=f)
        for nom in ('vision','identite'):
            dump = isole/(nom+'.dump'); dump.chmod(0o600)
            commande(age,'-r',config['recipient_age'],'-o',d/(nom+'.dump.age'),dump,timeout=120)
            os.chown(dump,postgres.pw_uid,postgres.pw_gid)
        etape('restauration_isolee')
        # Une réponse ambiguë du démarrage n'autorise pas à effacer un serveur.
        actif = True; preparation.initialiser_cluster(isole,b)
        def sql(base,texte):
            return commande(runuser,'-u','postgres','--',b/'psql','-XAtq','-v','ON_ERROR_STOP=1',
                '-h',isole,'-U','postgres','-d',base,'-f','-',env=environnement(),
                input=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n"+texte).encode()).strip()
        parametres = json.loads(sql('postgres',"SELECT json_build_object('tcp',current_setting('listen_addresses'),'socket',current_setting('unix_socket_directories'),'data',current_setting('data_directory'),'encodage',current_setting('server_encoding'),'majeure',current_setting('server_version_num')::int/10000);"))
        association.verifier_isole(str(isole),parametres)
        sql('postgres','CREATE ROLE vision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; CREATE DATABASE vision OWNER vision; CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT; CREATE DATABASE mrjam_identite OWNER keycloak;')
        commande(runuser,'-u','postgres','--',b/'pg_restore','--exit-on-error','-h',isole,'-U','postgres','-d','vision',isole/'vision.dump',env=environnement(),timeout=600)
        commande(runuser,'-u','postgres','--',b/'pg_restore','--exit-on-error','--no-owner','--no-privileges','--role=keycloak',
            '-h',isole,'-U','postgres','-d','mrjam_identite',isole/'identite.dump',env=environnement(),timeout=600)
        exiger(empreintes(lambda q:sql('vision',q),tables,acl) == avant and
            empreintes(lambda q:sql('mrjam_identite',q),tables_idp,acl) == idp_avant)
        exiger(sql('vision','SELECT count(*)=18 AND max(version)=18 FROM vision_schema_migrations;') == 't')
        etape('migrations_et_association_isolees')
        env = {**environnement(),'PGHOST':str(isole),'PGUSER':'postgres','PGDATABASE':'vision',
            'PATH':str(b)+':'+os.environ['PATH']}
        commande('sh',source/'scripts/migrate.sh',env=env,timeout=600)
        sql('vision',(source/'scripts/roles.sql').read_text())
        sql('vision',association.association_sql(identite,historique,acl.litteral))
        attendu = dict(comptes=1,administrateurs=1,identites=1,issuer=identite['issuer'],sujet=identite['sujet'],utilisateur=historique['utilisateur_historique'],inscriptions=False)
        obtenu = json.loads(sql('vision',"SELECT json_build_object('comptes',(SELECT count(*) FROM vision_gestion.comptes),'administrateurs',(SELECT count(*) FROM vision_gestion.comptes WHERE administrateur),'identites',(SELECT count(*) FROM vision_gestion.identites),'issuer',emetteur,'sujet',sujet,'utilisateur',utilisateur,'inscriptions',(SELECT inscriptions_ouvertes FROM vision_gestion.configuration)) FROM vision_gestion.identites;"))
        exiger(obtenu == attendu)
        exiger(sql('vision',"SELECT count(*)=0 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind IN ('r','p','v','m') AND has_table_privilege('vision_administration',c.oid,'SELECT,INSERT,UPDATE,DELETE');") == 't')
        exiger(sql('vision',"SELECT count(*)=0 FROM pg_roles WHERE rolname IN ('vision','vision_administration','vision_identite','vision_cycle','vision_admission','vision_fermeture') AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);") == 't')
        exiger(empreintes(lambda q:sql('vision',q),tables,acl) == avant)
        sauver('association-privee.json',dict(**identite,**historique,administrateur_applicatif=True,production=False))
        etape('retour_droits_isole')
        retour = acl.retour(releve)
        fd = os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: prive.ecrire(fd,'retour-acl.sql',retour)
        finally: os.close(fd)
        for _ in range(2):
            sql('vision',retour)
            apres = acl.relever(lambda q:sql('vision',q)); historiques = {(o['type'],o['nom']) for o in releve['objets']}
            exiger([o for o in apres['objets'] if (o['type'],o['nom']) in historiques] == releve['objets'] and apres['role'] == releve['role'])
            exiger(empreintes(lambda q:sql('vision',q),tables,acl) == avant)
    finally:
        if actif: commande(runuser,'-u','postgres','--',b/'pg_ctl','-D',isole/'data','-m','fast','-w','stop')
        shutil.rmtree(isole)
    etape('composants_garde_ferme')
    args = [ROOT/'scripts/vision-bascule-composants.nix','--argstr','configuration','/etc/nixos/configuration.nix',
        '--argstr','source',source,'--argstr','fournisseur',candidat['audit']['fournisseur'],'-I','nixpkgs='+candidat['audit']['nixpkgs']]
    compos = json.loads(commande('nix-instantiate','--eval','--strict','--json',*args,'--attr','resume'))
    exiger(compos['systeme_actif'] == activation['systeme_amorcage'] and compos['postgres_paquet'] == resume['postgres_paquet'] and
        compos['fournisseur_source'] == candidat['audit']['fournisseur'] and compos['garde_activation'] is True and
        all(compos[k] is False for k in ('preconditions_validees','generation_constructible','inscriptions','activation')))
    sauver('evaluation-privee.json',compos)
    lot = commande('nix-build',*args,'--attr','lot','--out-link',d/'composants','--max-jobs','1','--cores','2',timeout=1800).strip()
    exiger(lot == compos['lot'])
    etape('invariants_finaux')
    observateur.main(association.OBSERVATION, observer=True, activation_seule=True)
    rapport = dict(version=1,infrastructure=revision,observation=association.OBSERVATION,vision=candidat['vision'],style=candidat['style'],
        restauration_vision_reelle=True,restauration_identite_reelle=True,sujet_identite_conserve=True,credentials_identite_conserves=True,
        migrations_isolees_sans_perte=True,association_et_admin_isoles=True,retour_acl_rejoue=True,composants_construits=True,
        garde_activation=True,cle_personnelle_verifiee=False,copie_exterieure_verifiee=False,
        source_configuration_reparee=True,production_modifiee=REPARATION.SOURCE_MODIFIEE,
        donnees_production_modifiees=False,generation_active_modifiee=False,activation=False,inscriptions=False)
    sauver('preparation.json',rapport); print(json.dumps(rapport),flush=True)


if __name__ == '__main__':
    def interruption(*_): raise InterruptedError('Préparation interrompue')
    for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT): signal.signal(sig,interruption)
    p = argparse.ArgumentParser(); p.add_argument('revision'); a = p.parse_args()
    try: preparer(a.revision)
    except Exception:
        trace = traceback.format_exc()
        try: diagnostic(trace.encode())
        except Exception: pass
        try:
            lecteur = charger('projection_refus_bascule',ROOT/'scripts/vision-bascule-diagnostiquer.py')
            noms = ('vision-bascule-preparer.py','vision-multiutilisateur-preparer.py',
                'vision-configuration-reparer.py','vision-entree-configuration.py','vision-acl.py',
                'vision-proprietaire.py','vision-bascule-principaux.py')
            projection = lecteur.classer(trace,{n:(ROOT/'scripts'/n).read_text() for n in noms},ROOT.parent)
            print(json.dumps(dict(refus_bascule=projection)),flush=True)
        except Exception: pass
        print(json.dumps(dict(preparation_bascule_refusee=True,etape=ETAPE,
            production_modifiee=bool(REPARATION and REPARATION.SOURCE_MODIFIEE),donnees_production_modifiees=False,
            activation=False,inscriptions=False)),flush=True)
        raise SystemExit(1)
