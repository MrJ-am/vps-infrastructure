"""Qualifier le paquet construit avec systemd DynamicUser/peer, hors production."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('construction', ROOT / 'scripts/vision-identite-construire.py')
construction = importlib.util.module_from_spec(spec); spec.loader.exec_module(construction)
exiger = construction.exiger
ETAPE = 'demarrage'


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape': nom}), flush=True)


def commande(*args, entree=None, timeout=120):
    # Ne laisser aucune variable de connexion PG du runner orienter la cible.
    env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    try:
        r = subprocess.run([str(a) for a in args], input=entree, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise construction.ConstructionRefusee('Délai de qualification dépassé') from None
    if r.returncode:
        construction.preparation.diagnostic_prive(r.stderr)
        raise construction.ConstructionRefusee('Commande de qualification refusée')
    return r.stdout.decode().strip()


def preuve_construction(rapport, preuve, candidat, resume):
    cles = ('version', 'infrastructure', 'preparation', 'vision', 'style', 'keycloak',
        'paquet', 'plugins', 'construction', 'jdbc_unix_configure', 'jdbc_unix_vps_qualifie',
        'identite_initiale', 'activation', 'inscriptions')
    exiger(all(rapport.get(k) == preuve[k] for k in cles), 'Construction réelle différente ou incomplète')
    exiger(rapport['construction'] is True and rapport['jdbc_unix_configure'] is True and
        all(rapport[k] is False for k in ('jdbc_unix_vps_qualifie', 'identite_initiale', 'activation', 'inscriptions')),
        'Construction ou conditions inattendues')
    exiger(rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        rapport['paquet'] == resume['paquet'] and resume['version'] == '26.7.3' and
        resume['jdbc_unix'] is True and all(resume[k] is False for k in
            ('preconditions_validees', 'inscriptions', 'activation')), 'Candidat ou paquet différent')
    construction.store(rapport['paquet'])


def unite(nom, proprietes, args):
    return ['systemd-run', '--quiet', '--unit=' + nom, '--collect',
        *['--property=' + p for p in proprietes], '--', *[str(a) for a in args]]


def arreter(noms, runtimes):
    """Arrêter même après échec ; ne retirer aucun runtime encore utilisé."""
    erreurs = []
    for nom in noms:
        try:
            subprocess.run(['systemctl', 'stop', nom], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=45)
        except subprocess.TimeoutExpired: erreurs.append(nom)
    for nom in noms:
        r = subprocess.run(['systemctl', 'show', nom, '-p', 'MainPID', '--value'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        exiger(r.stdout.strip() in (b'', b'0'), 'Unité synthétique encore active')
    exiger(not erreurs, 'Arrêt des unités synthétiques incomplet')
    exiger(all(not p.exists() for p in runtimes), 'Runtime synthétique non retiré')


def qualifier(revision):
    global ETAPE
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Exécution Actions root identifiée requise')
    os.umask(0o077)
    d = Path('/root/vision-identite-unix-operations') / revision
    construction.dossier_prive(d.parent); construction.dossier_prive(d)
    exiger(ROOT == d / 'source', 'Source opérateur différente')
    construction.preparation.DIAGNOSTIC = d / 'diagnostic-prive.log'
    exiger(not (d / 'qualification.json').exists(), 'Qualification déjà terminée')
    candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
    preuve = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())
    etape('invariants_actifs'); configuration = construction.verifier_socle(candidat)
    etape('preuve_construction')
    exiger(re.fullmatch('[0-9a-f]{40}', preuve['infrastructure']), 'Révision de construction invalide')
    ancien = Path('/root/vision-identite-operations') / preuve['infrastructure']
    construction.dossier_prive(ancien.parent); construction.dossier_prive(ancien)
    rapport = construction.lire_prive(ancien / 'construction.json')
    resume = json.loads(commande('nix-instantiate', '--eval', '--strict', '--json',
        ROOT / 'scripts/vision-identite-paquet.nix', '--attr', 'resume', '-I', 'nixpkgs=' + candidat['audit']['nixpkgs']))
    preuve_construction(rapport, preuve, candidat, resume)
    preparation = json.loads((ROOT / 'operations/vision-multiutilisateur-qualification.json').read_text())
    ancien_pg = Path('/root/vision-multiutilisateur-operations') / preparation['infrastructure']
    construction.dossier_prive(ancien_pg.parent); construction.dossier_prive(ancien_pg)
    construction.preuve_preparation(construction.lire_prive(ancien_pg / 'preparation.json'), preparation, candidat)
    paquet = Path(rapport['paquet']); exiger(paquet.is_dir(), 'Paquet construit absent')
    pg = Path(construction.store(configuration['postgres_paquet'])) / 'bin'
    exiger(commande(pg / 'postgres', '--version').startswith('postgres (PostgreSQL) 17.'), 'PostgreSQL natif différent')
    disponible = next(int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
    exiger(disponible >= 3 * 1024 * 1024, 'Mémoire disponible insuffisante')
    suffixe = revision[:12]
    idp = 'mrjam-q-idp-' + suffixe; postgres = 'mrjam-q-pg-' + suffixe
    r_idp = Path('/run') / idp; r_pg = Path('/run') / postgres
    source = Path('/run/mrjam-q-source-' + suffixe)
    for nom in (idp, postgres):
        exiger(commande('systemctl', 'show', nom + '.service', '-p', 'LoadState', '--value') == 'not-found',
            'Unité synthétique déjà présente')
    try: pwd.getpwnam(idp)
    except KeyError: pass
    else: raise construction.ConstructionRefusee('Identité système déjà présente')
    exiger(all(not p.exists() and not p.is_symlink() for p in (source, r_pg, r_idp)), 'Runtime synthétique déjà présent')
    secret = secrets.token_urlsafe(32)
    (d / 'bootstrap').write_text(secret); (d / 'bootstrap').chmod(0o600)
    # Seuls deux lanceurs sans secret sont traversables par les utilisateurs
    # transitoires. Les rapports et logs restent dans le dossier root 0700.
    source.mkdir(mode=0o711)
    for nom in ('demarrer', 'postgresql'):
        fichier = source / (nom + '.sh')
        shutil.copyfile(ROOT / ('scripts/vision-identite-unix-' + nom + '.sh'), fichier); fichier.chmod(0o444)
    logs = {}
    for nom in ('idp', 'pg'):
        logs[nom] = d / (nom + '-prive.log'); logs[nom].touch(mode=0o600, exist_ok=False)
    commun = ['NoNewPrivileges=yes', 'PrivateNetwork=yes', 'PrivateTmp=yes',
        'ProtectSystem=strict', 'ProtectHome=yes', 'TimeoutStopSec=30', 'KillMode=control-group',
        'Environment=PATH=/run/current-system/sw/bin']
    def sql(texte, role='postgres', base='postgres'):
        return commande('runuser', '-u', 'postgres', '--', pg / 'psql', '-XAtq',
            '-v', 'ON_ERROR_STOP=1', '-h', r_pg / 'socket', '-U', role, '-d', base, '-c', texte)
    try:
        etape('cluster_synthetique_peer')
        commande(*unite(postgres, [*commun, 'Type=exec', 'User=postgres', 'Group=postgres',
            'RuntimeDirectory=' + postgres, 'RuntimeDirectoryMode=0711', 'RuntimeMaxSec=480',
            'KillSignal=SIGINT', 'StandardOutput=append:' + str(logs['pg']), 'StandardError=append:' + str(logs['pg'])],
            ['/bin/sh', source / 'postgresql.sh', pg, r_pg, idp]))
        for _ in range(60):
            try:
                if sql('SELECT 1') == '1': break
            except construction.ConstructionRefusee: time.sleep(1)
        else: raise construction.ConstructionRefusee('Cluster synthétique indisponible')
        exiger(sql("SELECT current_setting('server_encoding')='UTF8' AND current_setting('listen_addresses')='' AND current_setting('server_version_num')::int BETWEEN 170000 AND 179999") == 't', 'Cluster synthétique incompatible')
        sql('CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
        sql('CREATE DATABASE identite_unix OWNER keycloak')
        sql('REVOKE ALL ON DATABASE identite_unix FROM PUBLIC')
        exiger(sql("SELECT rolpassword IS NULL AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolbypassrls FROM pg_authid WHERE rolname='keycloak'") == 't', 'Rôle synthétique trop privilégié')
        etape('demarrage_native_dynamic_user')
        commande(*unite(idp, [*commun, 'Type=notify', 'NotifyAccess=all', 'DynamicUser=yes',
            'User=' + idp, 'Group=' + idp, 'RuntimeDirectory=' + idp, 'RuntimeDirectoryMode=0700',
            'RuntimeMaxSec=240', 'MemoryMax=2G', 'TimeoutStartSec=180',
            'LoadCredential=bootstrap:' + str(d / 'bootstrap'),
            'StandardOutput=append:' + str(logs['idp']), 'StandardError=append:' + str(logs['idp'])],
            ['/bin/sh', source / 'demarrer.sh', paquet, r_idp, r_pg / 'socket']))
        for _ in range(30):
            pid = commande('systemctl', 'show', idp, '-p', 'MainPID', '--value')
            if pid.isdigit() and int(pid) > 1: break
            time.sleep(1)
        else: raise construction.ConstructionRefusee('Processus natif absent')
        proprietes = dict(l.split('=', 1) for l in commande('systemctl', 'show', idp,
            '-p', 'DynamicUser', '-p', 'PrivateNetwork', '-p', 'User').splitlines())
        exiger(proprietes == dict(DynamicUser='yes', PrivateNetwork='yes', User=idp), 'Isolation systemd différente')
        exiger(Path('/proc/' + pid + '/ns/net').stat().st_ino != Path('/proc/1/ns/net').stat().st_ino, 'Réseau privé absent')
        utilisateur = pwd.getpwnam(idp)
        uid = next(l for l in Path('/proc/' + pid + '/status').read_text().splitlines() if l.startswith('Uid:')).split()[2]
        exiger(int(uid) == utilisateur.pw_uid and utilisateur.pw_uid != 0, 'Utilisateur dynamique absent')
        etape('http_prive_et_spi')
        http = json.loads(commande('nsenter', '--target', pid, '--net', '--', sys.executable,
            ROOT / 'scripts/vision-identite-unix-http.py', entree=json.dumps({'secret': secret}).encode(), timeout=160))
        exiger(all(http.get(k) is True for k in ('demarrage_optimise', 'version_native', 'spi_charge',
            'inscription_native_fermee', 'api_synthetique')), 'Qualification HTTP native incomplète')
        etape('verification_peer')
        exiger(sql("SELECT count(*)>0 FROM pg_stat_activity WHERE usename='keycloak' AND datname='identite_unix' AND client_addr IS NULL") == 't', 'Connexion JDBC Unix absente')
        exiger(sql("SELECT count(*)=1 FROM pg_hba_file_rules WHERE auth_method='peer' AND 'keycloak'=ANY(user_name)") == 't', 'Authentification peer absente')
        mauvais = subprocess.run(['runuser', '-u', 'postgres', '--', str(pg / 'psql'), '-XAtq',
            '-h', str(r_pg / 'socket'), '-U', 'keycloak', '-d', 'identite_unix', '-c', 'SELECT 1'],
            env={k: v for k, v in os.environ.items() if not k.startswith('PG')},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        exiger(mauvais.returncode != 0, 'Un autre utilisateur système peut accéder à la base')
    finally:
        interrompue = ETAPE
        etape('arret_et_nettoyage')
        try: arreter([idp + '.service', postgres + '.service'], [r_idp, r_pg])
        finally:
            (d / 'bootstrap').unlink(missing_ok=True)
            shutil.rmtree(source)
        # Conserver l'étape du refus initial si le nettoyage a réussi.
        ETAPE = interrompue
    etape('invariants_finaux'); construction.verifier_socle(candidat)
    resultat = dict(version=1, infrastructure=revision, construction=preuve['infrastructure'],
        vision=candidat['vision'], style=candidat['style'], keycloak='26.7.3', paquet=str(paquet),
        **http, jdbc_unix_vps_qualifie=True, peer_sans_mot_de_passe=True, autre_uid_refuse=True,
        dynamic_user=True, reseau_prive=True, postgresql_tcp_ferme=True, runtimes_retires=True,
        identite_initiale=False, activation=False, inscriptions=False)
    construction.preparation.sauver(d / 'qualification.json', resultat)
    print(json.dumps(resultat), flush=True)


def controler(revision):
    """Après une réussite ou un échec : socle et absence d'unité résiduelle."""
    exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Constat Actions root identifié requis')
    construction.verifier_socle(json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text()))
    for prefixe in ('mrjam-q-idp-', 'mrjam-q-pg-'):
        nom = prefixe + revision[:12]
        exiger(commande('systemctl', 'show', nom + '.service', '-p', 'MainPID', '--value') in ('', '0'),
            'Unité synthétique encore active')
        exiger(not (Path('/run') / nom).exists(), 'Runtime synthétique encore présent')
    print(json.dumps(dict(socle_inchange=True, runtimes_retires=True, activation=False)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('revision')
    p.add_argument('--controler', action='store_true'); a = p.parse_args()
    try: (controler if a.controler else qualifier)(a.revision)
    except Exception as erreur:
        try: construction.preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        r = dict(qualification='interrompue', etape=ETAPE, activation=False, donnees_affichees=False)
        if isinstance(erreur, construction.ConstructionRefusee): r['raison'] = str(erreur)
        print(json.dumps(r), file=sys.stderr); sys.exit(1)
