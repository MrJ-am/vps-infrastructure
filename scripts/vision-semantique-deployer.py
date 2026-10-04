#!/usr/bin/env python3
"""Publication Vision 2.5 : construction, restauration isolée, essai et retour.

Les rapports ne contiennent que des empreintes et agrégats. Aucun dump restauré
en production ; les écritures métier nouvelles sont conservées lors d'un retour.
"""
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

APPLICATION = 'c0bfcac66b9ee52e282bb895ec6aed3921a86266'
SYSTEME_AVANT = '/nix/store/mabshi6mmisnabl5qb5hwldnkxiz2s25-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
NIXPKGS = '/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
MODELE = 'contenu-fenetres-1:8e4f52f33f8935f81b1869cc081834734f01f2383e1e1e5813aff156649b42e4'


def exiger(condition, message):
    if not condition:
        raise RuntimeError(message)


def executer(*args, entree=None, env=None, cwd=None):
    resultat = subprocess.run([str(a) for a in args], input=entree, env=env, cwd=cwd,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if resultat.returncode:
        erreur = os.environ.get('VISION_DEPLOIEMENT_ERREUR')
        if erreur:
            Path(erreur).write_bytes(resultat.stderr)
        raise RuntimeError('Commande refusée : ' + Path(str(args[0])).name + ' ; journal privé sur le VPS.')
    return resultat.stdout


def sauver(path, valeur):
    temporaire = path.with_suffix('.nouveau')
    temporaire.write_text(json.dumps(valeur, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporaire, path)


def empreinte(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dossier(revision):
    exiger(re.fullmatch('[0-9a-f]{40}', revision), 'Révision exacte requise')
    return Path('/root/vision-semantique') / revision


def etat():
    return dict(systeme=str(Path('/run/current-system').resolve()),
                demarrage=str(Path('/nix/var/nix/profiles/system').resolve()),
                configuration=empreinte(Path('/etc/nixos/configuration.nix')),
                **{n: str(Path('/srv/' + n + '/current').resolve())
                   for n in ('vision', 'vision-interface', 'matheval', 'logique')})


def services():
    executer('systemctl', 'is-active', 'sshd', 'nginx', 'postgresql', 'matheval', 'vision',
             'mrj-auth', 'phpfpm-nextcloud', 'redis-nextcloud', 'nextcloud-backup.timer',
             'postgresqlBackup-vision.timer', 'postgresqlBackup-matheval.timer')


def sql(requete, base='vision', socket='/run/postgresql', port=5432, postgres=None):
    psql = str(Path(postgres) / 'bin/psql') if postgres else shutil.which('psql')
    return executer('runuser', '-u', 'postgres', '--', psql, '-XAtq', '-v', 'ON_ERROR_STOP=1',
                    '-h', socket, '-p', port, '-d', base, '--file=-', entree=requete.encode())


def donnees(**connexion):
    tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' "
                 "AND tablename NOT IN ('vision_schema_migrations','vision_embeddings','vision_preparations_items') ORDER BY tablename",
                 **connexion).decode().splitlines()
    exiger(all(re.fullmatch('vision_[a-z_]+', n) for n in tables), 'Table inconnue')
    return {table: sql("SELECT md5(coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text FROM "
                       + table + " t),'[]'))", **connexion).decode().strip() for table in tables}


def sauvegarder(d, nom):
    cible = d / (nom + '.dump')
    with cible.open('wb') as fichier:
        resultat = subprocess.run(['runuser', '-u', 'postgres', '--', shutil.which('pg_dump'),
                                  '-Fc', '-h', '/run/postgresql', '-d', 'vision'], stdout=fichier,
                                 stderr=subprocess.PIPE)
    exiger(resultat.returncode == 0 and cible.stat().st_size > 0, 'Sauvegarde refusée')
    return cible


def lien(cible, courant):
    nouveau = Path(courant + '.semantique')
    nouveau.unlink(missing_ok=True)
    nouveau.symlink_to(cible)
    os.replace(nouveau, courant)


def evaluer(source, configuration):
    return json.loads(executer('nix-instantiate', '--eval', '--strict', '--json',
                              source / 'scripts/vision-semantique-config.nix', '--argstr',
                              'configuration', configuration, '-I', 'nixpkgs=' + NIXPKGS))


def fournir(url, contenu='Initialisation du fournisseur'):
    requete = urllib.request.Request(url, data=json.dumps({'contenu': contenu}).encode(),
                                    headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.load(reponse)


def attendre_fournisseur(url):
    for _ in range(90):
        try:
            exiger(fournir(url)['modele'] == MODELE, 'Snapshot du modèle différent')
            return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise RuntimeError('Fournisseur indisponible')


def vectoriser(application, environnement):
    total = 0
    for _ in range(100):
        sortie = executer(sys.executable, application / 'scripts/backfill_embeddings.py',
                          '--limite', '100', env=environnement)
        nombre = json.loads(sortie)['embeddings_calcules']
        total += nombre
        if nombre == 0:
            return total
    raise RuntimeError('Backfill non terminé après cent lots')


def restauration(d, r, dump, nom):
    """Cluster PostgreSQL séparé, sans TCP, supprimé après essais métier."""
    cluster = Path('/var/lib/postgresql') / ('vision-semantique-' + d.name[:12])
    exiger(not cluster.exists(), 'Cluster de test déjà présent')
    cluster.mkdir(mode=0o700)
    executer('chown', 'postgres:postgres', cluster)
    pg = Path(r['apres']['postgres']) / 'bin'
    executer('runuser', '-u', 'postgres', '--', pg / 'initdb', '-D', cluster / 'data', '--auth=trust', '--no-locale', '-E', 'UTF8')
    socket = cluster / 'socket'
    socket.mkdir(mode=0o700)
    executer('chown', 'postgres:postgres', socket)
    demarre = False
    fournisseur = serveur = None
    logs = []
    try:
        executer('runuser', '-u', 'postgres', '--', pg / 'pg_ctl', '-D', cluster / 'data', '-l', cluster / 'postgres.log',
                 '-o', '-k ' + str(socket) + " -p 39015 -c listen_addresses=''", '-w', 'start')
        demarre = True
        connexion = dict(socket=str(socket), port=39015, postgres=r['apres']['postgres'])
        sql('CREATE ROLE vision LOGIN; CREATE DATABASE vision_semantique_test OWNER vision;', base='postgres', **connexion)
        connexion['base'] = 'vision_semantique_test'
        with dump.open('rb') as fichier:
            resultat = subprocess.run(['runuser', '-u', 'postgres', '--', str(pg / 'pg_restore'), '--exit-on-error',
                                      '--no-owner', '--role=vision', '-h', str(socket), '-p', '39015',
                                      '-d', 'vision_semantique_test'], stdin=fichier, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if resultat.returncode:
            (d / 'restauration-erreur-privee.log').write_bytes(resultat.stderr)
        exiger(resultat.returncode == 0, 'Restauration isolée refusée')
        avant = donnees(**connexion)
        sql('CREATE EXTENSION vector;', **connexion)
        application = Path(r['serveur'])
        sql('SET ROLE vision;\n' + (application / 'migrations/016_creation_semantique.sql').read_text(), **connexion)
        exiger(donnees(**connexion) == avant, 'Migration ayant modifié une donnée historique')
        exiger(sql('SELECT vision_creation_contrat();', **connexion).strip() == b'1', 'Contrat de création incohérent')
        wrapper = d / 'psql-isole'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(pg / 'psql'))
                           + ' -h ' + shlex.quote(str(socket)) + ' -p 39015 -U postgres -d vision_semantique_test "$@"\n')
        wrapper.chmod(0o700)
        env = {**os.environ, 'PGHOST': '127.0.0.1', 'PGDATABASE': 'vision_semantique_test',
               'VISION_PSQL': str(wrapper), 'VISION_DATABASE_TEST_PORT': '39013',
               'VISION_EMBEDDINGS_URL': 'http://127.0.0.1:39014/embedding', 'OMP_NUM_THREADS': '2',
               'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
               'IP': '127.0.0.1', 'PORT': '39013'}
        for n in ('fournisseur', 'serveur'):
            logs.append((d / (nom + '-' + n + '-prive.log')).open('wb'))
        fournisseur = subprocess.Popen(shlex.split(r['apres']['fournisseur']) + ['--port', '39014'],
                                       env=env, stdout=logs[0], stderr=logs[0])
        attendre_fournisseur(env['VISION_EMBEDDINGS_URL'])
        calcules = vectoriser(application, env)
        exiger(donnees(**connexion) == avant, 'Backfill ayant modifié une donnée historique')
        serveur = subprocess.Popen([str(application / 'vision')], cwd=application, env=env, stdout=logs[1], stderr=logs[1])
        for _ in range(30):
            try:
                with urllib.request.urlopen('http://127.0.0.1:39013/healthz', timeout=2):
                    break
            except OSError:
                time.sleep(1)
        for test in ('tests/qualite_creation.py', 'tests/check_creation.py'):
            executer(sys.executable, application / test, cwd=application, env=env)
        qualite = json.loads((application / 'qualite-creation.json').read_text())
        exiger(qualite['rappel'] == 1 and qualite['modele'] == MODELE, 'Qualification sémantique insuffisante')
        rapport = dict(restauration_verifiee=True, tables_preservees=len(avant), embeddings_calcules=calcules,
                       rappel=qualite['rappel'], rang_moyen=qualite['rang_moyen'],
                       faux_positifs_moyens=qualite['faux_positifs_moyens'], preuves_verifiees=True,
                       modele=MODELE, sauvegarde_sha256=empreinte(dump), sauvegarde_octets=dump.stat().st_size)
        sauver(d / (nom + '-rapport.json'), rapport)
        return rapport
    finally:
        for processus in (serveur, fournisseur):
            if processus:
                processus.terminate()
                try:
                    processus.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    processus.kill()
                    processus.wait()
        for fichier in logs:
            fichier.close()
        if demarre:
            executer('runuser', '-u', 'postgres', '--', pg / 'pg_ctl', '-D', cluster / 'data', '-m', 'fast', '-w', 'stop')
        shutil.rmtree(cluster)


def preparer(revision):
    d = dossier(revision)
    source = d / 'source'
    exiger(not (d / 'preparation.json').exists(), 'Opération déjà préparée')
    avant = etat()
    exiger(avant['systeme'] == SYSTEME_AVANT and avant['demarrage'] == SYSTEME_AVANT, 'Génération différente de l’audit')
    exiger(executer('nix-instantiate', '--find-file', 'nixpkgs').decode().strip() == NIXPKGS, 'Nixpkgs différent')
    services()
    exiger(shutil.disk_usage('/').free > 15 * 1024**3, 'Espace disque insuffisant')
    demande = json.loads((source / 'operations/vision-semantique-candidat.json').read_text())
    exiger(demande['application'] == APPLICATION, 'Révision applicative différente')
    for fichier, sha in demande['fichiers'].items():
        exiger(empreinte(source / fichier) == sha, 'Archive différente du candidat validé')
    application = Path('/srv/vision/releases') / APPLICATION
    if application.exists():
        exiger((application / 'revision-application.txt').read_text().strip() == APPLICATION, 'Release existante différente')
    application.mkdir(mode=0o755, parents=True, exist_ok=True)
    with tarfile.open(source / 'vendor/vision-semantique-source.tar.gz') as archive:
        for membre in archive.getmembers():
            exiger(not membre.issym() and not membre.islnk() and (application / membre.name).resolve().is_relative_to(application), 'Archive non sûre')
        archive.extractall(application, filter='data')
    exiger((application / 'revision-application.txt').read_text().strip() == APPLICATION, 'Source non conforme')
    executer('nix-shell', '-I', 'nixpkgs=' + NIXPKGS, '-p', 'sbcl', '--run', 'cd ' + shlex.quote(str(application)) + ' && sh build.sh')
    exiger((application / 'vision').stat().st_size > 1000000, 'Binaire absent')
    executer('chmod', '-R', 'a+rX', application)
    statique = Path('/srv/vision-interface/releases') / APPLICATION
    statique.mkdir(mode=0o755, parents=True, exist_ok=True)
    with zipfile.ZipFile(source / 'vendor/vision-semantique-interface.zip') as archive:
        for nom in archive.namelist():
            exiger((statique / nom).resolve().is_relative_to(statique), 'Archive statique non sûre')
        archive.extractall(statique)
    manifeste = json.loads((statique / 'manifest.json').read_text())
    exiger(manifeste['revisionApplication'] == APPLICATION, 'Interface non conforme')
    for fichier, sha in manifeste['fichiers'].items():
        exiger(empreinte(statique / fichier) == sha, 'Empreinte statique non conforme')
    executer('chmod', '-R', 'a+rX', statique)
    config = source / 'hosts/hostinger/vision-semantique.nix'
    configuration_avant = evaluer(source, '/etc/nixos/configuration.nix')
    apres = evaluer(source, str(config))
    exiger(configuration_avant['systeme'] == avant['systeme'], 'Sources actives différentes de la génération')
    exiger(configuration_avant['invariant'] == apres['invariant'], 'Invariant système modifié')
    racines = Path('/nix/var/nix/gcroots/vision-semantique') / revision
    racines.mkdir(parents=True)
    (racines / 'avant').symlink_to(avant['systeme'])
    executer('nix-build', '<nixpkgs/nixos>', '-A', 'system', '-I', 'nixpkgs=' + NIXPKGS,
             '-I', 'nixos-config=' + str(config), '--out-link', racines / 'apres')
    exiger(str((racines / 'apres').resolve()) == apres['systeme'], 'Construction différente de l’évaluation')
    plan = executer(Path(apres['systeme']) / 'bin/switch-to-configuration', 'dry-activate').decode()
    (d / 'plan-prive.txt').write_text(plan)
    for ligne in plan.splitlines():
        if 'stopping the following units:' in ligne or 'restarting the following units:' in ligne:
            exiger(not re.search(r'(sshd|systemd-networkd|matheval|mrj-auth|phpfpm-nextcloud|redis-nextcloud)\.service', ligne), 'Redémarrage critique imprévu')
    commande = shlex.split(apres['nginx'])
    executer(commande[0], '-t', '-c', commande[commande.index('-c') + 1])
    shutil.copy2('/etc/nixos/configuration.nix', d / 'configuration-avant.nix', follow_symlinks=False)
    r = dict(revision=revision, application=APPLICATION, avant=avant, apres=apres,
             serveur=str(application), interface=str(statique), python=sys.executable, chemin=os.environ['PATH'])
    dump = sauvegarder(d, 'preparation')
    rapport = restauration(d, r, dump, 'preparation')
    temoin = d / 'timer-verifie'
    executer('systemd-run', '--unit=vision-semantique-temoin-' + revision[:12], '--on-active=2s', '--timer-property=AccuracySec=1s',
             shutil.which('touch'), temoin)
    for _ in range(20):
        if temoin.exists():
            break
        time.sleep(1)
    exiger(temoin.exists(), 'Timer autonome non vérifié')
    exiger(etat() == avant, 'État actif modifié pendant la préparation')
    services()
    sauver(d / 'preparation.json', r)
    print(json.dumps(rapport, ensure_ascii=False))


def lire(revision):
    d = dossier(revision)
    return d, json.loads((d / 'preparation.json').read_text())


def retour(revision):
    d, r = lire(revision)
    if (d / 'enregistre').exists():
        return
    subprocess.run(['systemctl', 'stop', 'vision-semantique-appliquer-' + revision[:12]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with (d / 'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        if (d / 'enregistre').exists():
            return
        exiger((d / 'engage').exists(), 'Aucune activation engagée')
        exiger(etat()['matheval'] == r['avant']['matheval'] and etat()['logique'] == r['avant']['logique'], 'Publication concurrente')
        (d / 'retour-engage').touch()
        executer('systemctl', 'stop', 'vision', 'vision-embeddings')
        lien(r['avant']['vision'], '/srv/vision/current')
        lien(r['avant']['vision-interface'], '/srv/vision-interface/current')
        # Les fonctions SQL et vecteurs nouveaux restent présents : le serveur
        # précédent peut lire et réviser, mais son ancien protocole ne crée plus.
        executer('cp', '-a', d / 'configuration-avant.nix', '/etc/nixos/configuration.semantique-retour')
        executer('mv', '-Tf', '/etc/nixos/configuration.semantique-retour', '/etc/nixos/configuration.nix')
        executer('nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', r['avant']['demarrage'])
        executer(Path(r['avant']['systeme']) / 'bin/switch-to-configuration', 'switch')
        executer('systemctl', 'start', 'vision')
        services()
        sauver(d / 'retour.json', dict(etat=etat(), restauration_base=False, donnees_conservees=True))
    executer('systemctl', 'stop', 'vision-semantique-retour-' + revision[:12] + '.timer')


def appliquer(revision):
    d, r = lire(revision)
    with (d / 'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        exiger(etat() == r['avant'] and not (d / 'retour-engage').exists(), 'État modifié depuis préparation')
        executer('systemctl', 'stop', 'vision')
        dump = sauvegarder(d, 'activation')
        rapport = restauration(d, r, dump, 'activation')
        avant = donnees()
        executer(Path(r['apres']['systeme']) / 'bin/switch-to-configuration', 'test')
        executer('systemctl', 'stop', 'vision')
        exiger(sql("SELECT count(*) FROM pg_extension WHERE extname='vector'").strip() == b'1', 'Extension pgvector non activée')
        sql('SET ROLE vision;\n' + (Path(r['serveur']) / 'migrations/016_creation_semantique.sql').read_text())
        attendre_fournisseur('http://127.0.0.1:39004/embedding')
        wrapper = d / 'psql-production'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(shutil.which('runuser')) + ' -u vision -- '
                           + shlex.quote(str(Path(r['apres']['postgres']) / 'bin/psql')) + ' -h /run/postgresql -d vision "$@"\n')
        wrapper.chmod(0o700)
        env = {**os.environ, 'VISION_PSQL': str(wrapper), 'VISION_EMBEDDINGS_URL': 'http://127.0.0.1:39004/embedding'}
        total = vectoriser(Path(r['serveur']), env)
        exiger(donnees() == avant, 'Une donnée métier a changé pendant migration/backfill')
        exiger(sql('SELECT vision_creation_contrat(); SELECT vision_revision_contrat();').strip() == b'1\n6', 'Contrats SQL incohérents')
        lien(r['serveur'], '/srv/vision/current')
        lien(r['interface'], '/srv/vision-interface/current')
        executer('systemctl', 'start', 'vision')
        services()
        sauver(d / 'essai.json', dict(etat=etat(), rapport=rapport, embeddings_calcules=total, donnees_preservees=True))
        print('Essai sous retour autonome : données historiques conservées, embeddings calculés, application 2.5 démarrée.')


def demarrer(revision):
    d, r = lire(revision)
    exiger(not any((d / nom).exists() for nom in ('engage', 'retour-engage', 'enregistre')), 'Opération déjà engagée')
    exiger(etat() == r['avant'], 'Nouvel audit requis')
    (d / 'engage').touch()
    script = d / 'source/scripts/vision-semantique-deployer.py'
    executer('systemd-run', '--unit=vision-semantique-retour-' + revision[:12], '--on-active=30m', '--timer-property=AccuracySec=1s',
             '--setenv=PATH=' + r['chemin'], r['python'], script, 'retour', revision)
    executer('systemctl', 'is-active', 'vision-semantique-retour-' + revision[:12] + '.timer')
    executer('systemd-run', '--wait', '--pipe', '--unit=vision-semantique-appliquer-' + revision[:12],
             '--setenv=PATH=' + r['chemin'], r['python'], script, 'appliquer', revision)


def finaliser(revision):
    d, r = lire(revision)
    with (d / 'bascule.lock').open('a') as verrou:
        fcntl.flock(verrou, fcntl.LOCK_EX)
        exiger((d / 'essai.json').exists() and not (d / 'retour-engage').exists(), 'Essai absent ou retour engagé')
        attendu = {**r['avant'], 'systeme': r['apres']['systeme'], 'vision': r['serveur'], 'vision-interface': r['interface']}
        exiger(etat() == attendu, 'État différent du candidat')
        services()
        executer('systemctl', 'is-active', 'vision-semantique-retour-' + revision[:12] + '.timer')
        configuration = d / 'source/hosts/hostinger/vision-semantique.nix'
        temporaire = Path('/etc/nixos/configuration.semantique-final')
        temporaire.write_text('{ imports = [ ' + str(configuration) + ' ]; }\n')
        os.replace(temporaire, '/etc/nixos/configuration.nix')
        executer('nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', r['apres']['systeme'])
        executer(Path(r['apres']['systeme']) / 'bin/switch-to-configuration', 'boot')
        exiger(str(Path('/nix/var/nix/profiles/system').resolve()) == r['apres']['systeme'], 'Profil non enregistré')
        rapport = json.loads((d / 'essai.json').read_text())
        sauver(d / 'termine.json', dict(revision=revision, application=APPLICATION, etat=etat(), **{k: v for k, v in rapport.items() if k != 'etat'}))
        (d / 'enregistre').touch()
    executer('systemctl', 'stop', 'vision-semantique-retour-' + revision[:12] + '.timer')
    print('Publication enregistrée ; retour désarmé et anciennes générations conservées.')


if __name__ == '__main__':
    exiger(os.geteuid() == 0, 'Runner administratif requis')
    os.umask(0o077)
    os.environ['VISION_DEPLOIEMENT_ERREUR'] = str(dossier(sys.argv[2]) / 'commande-echec-prive.log')
    {'preparer': preparer, 'demarrer': demarrer, 'appliquer': appliquer,
     'retour': retour, 'finaliser': finaliser}[sys.argv[1]](sys.argv[2])
