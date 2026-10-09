"""Essai réservé sous systemd, retour autonome et enregistrement après contrôles."""
import argparse
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
import shutil
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


preparer = charger('amorcage_prepare', 'vision-identite-amorcage-preparer.py')
construction = preparer.construction
identite = preparer.composants.initial.identite
controle = charger('amorcage_controle', 'identite-amorcage-controle.py')
exiger = construction.exiger
SERVICES = ('sshd', 'postgresql', 'vision', 'matheval', 'mrj-auth')


def etape(nom):
    global ETAPE
    ETAPE = nom; print(json.dumps({'etape': nom}), flush=True)


def entree_nix(original, module, fournisseur):
    for p in (original, module):
        exiger(re.fullmatch(r'/[A-Za-z0-9/_.-]+\.nix', str(p)), 'Entrée NixOS non conforme')
    source = ''
    if fournisseur is not None:
        construction.store(fournisseur)
        source = 'services.visionEmbeddings.source = lib.mkForce (builtins.storePath ' + json.dumps(fournisseur) + ');'
    return '{ lib, ... }: { imports = [ ' + json.dumps(str(original)) + ' ' + json.dumps(str(module)) + ' ];\n' + \
        'infrastructure.amorcageIdentite.enable = true;\n' + source + '\n}\n'


def verifier_dry(texte):
    exiger('would activate the configuration' in texte and len(texte) < 1048576,
        'Dry-activate absent ou incomplet')
    exiger(not re.search(r'would (?:restart systemd|stop swap)', texte), 'Interruption du socle annoncée')
    autorises = {'nginx.service', 'nginx-config-reload.service',
        'systemd-journald@identite.service', 'systemd-journald@identite.socket',
        'systemd-journald-varlink@identite.socket', 'mrjam-amorcage-identite.service',
        'mrjam-amorcage-postgresql.service', 'mrjam-amorcage-sauvegarde.service',
        'mrjam-amorcage-sauvegarde.timer'}
    modifies = set()
    for action, noms in re.findall(r'would (stop|restart|reload) the following units: ([^\n]+)', texte):
        unites = {u.strip() for u in noms.split(',')}
        exiger(all(u in autorises or u.startswith('acme-') for u in unites),
            'Dry-activate annonce une unité étrangère à l’amorçage')
        modifies.update(unites)
    return len(modifies)


def script_retour(d, ancien, demarrage, outils, configuration='/etc/nixos/configuration.nix', profil='/nix/var/nix/profiles/system', courant='/run/current-system', worker=''):
    """Pas de Python/candidat/réseau/SQL requis par le retour ; verrou bref commun."""
    q = shlex.quote
    a = lambda nom: q(str(outils / nom))
    return f'''#!{outils}/bash
set -euo pipefail
umask 077
export PATH={q(str(outils)+':/run/wrappers/bin')}
exec 9>{q(str(d/'finalisation.lock'))}
{a('flock')} 9
test ! -e {q(str(d/'enregistre'))} || exit 0
test ! -e {q(str(d/'retour-termine'))} || exit 0
{a('touch')} {q(str(d/'retour-commence'))}
{a('systemctl')} stop {q(worker)} || true
{a('cp')} -a --no-dereference {q(str(d/'configuration-avant.nix'))} {q(configuration+'.retour')}
{a('mv')} -Tf {q(configuration+'.retour')} {q(configuration)}
{a('nix-env')} --profile {q(profil)} --set {q(demarrage)}
{q(demarrage+'/bin/switch-to-configuration')} boot
{q(ancien+'/bin/switch-to-configuration')} test
{a('systemctl')} is-active sshd nginx postgresql vision matheval mrj-auth
test "$({a('readlink')} -f {q(courant)})" = {q(ancien)}
test "$({a('readlink')} -f {q(profil)})" = {q(demarrage)}
{a('touch')} {q(str(d/'retour-termine'))}
'''


def preuve_valide(rapport, preuve, candidat):
    exiger(rapport == preuve and rapport['systeme_actif'] == candidat['audit']['systeme'] and
        rapport['vision'] == candidat['vision'] and rapport['style'] == candidat['style'] and
        rapport['proprietaires'] == 1 and rapport['authentification_unique'] is True and
        all(rapport[k] is True for k in ('construction', 'unites_conservees', 'hotes_conserves',
            'postgres_production_conserve', 'cluster_independant')) and
        all(rapport[k] is False for k in ('mode_vision_oidc', 'preconditions_validees',
            'identite_humaine', 'activation', 'inscriptions')), 'Construction réservée non qualifiée')
    construction.store(rapport['systeme_amorcage'])


def secret_amorcage(fd):
    try: secret = identite.lire(fd, 'amorcage-admin.secret', 128)
    except FileNotFoundError:
        secret = secrets.token_urlsafe(32) + '\n'; identite.ecrire(fd, 'amorcage-admin.secret', secret)
    exiger(re.fullmatch(r'[A-Za-z0-9_-]{43}\n', secret), 'Credential technique non conforme')


class Essai:
    def __init__(self, revision):
        exiger(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'Opérateur root Actions identifié requis')
        os.umask(0o077)
        self.revision = revision
        self.d = Path('/root/vision-identite-amorcage-essais') / revision
        construction.dossier_prive(self.d.parent); construction.dossier_prive(self.d)
        exiger(ROOT == self.d / 'source', 'Source opérateur différente')
        construction.preparation.DIAGNOSTIC = self.d / 'diagnostic-prive.log'
        self.fd = os.open(self.d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        self.preuve = json.loads((ROOT / 'operations/vision-identite-amorcage-qualification.json').read_text())
        exiger(re.fullmatch('[0-9a-f]{40}', self.preuve['infrastructure']), 'Révision préparée invalide')
        self.prepare = Path('/root/vision-identite-amorcage-operations') / self.preuve['infrastructure']
        construction.dossier_prive(self.prepare.parent); construction.dossier_prive(self.prepare)
        self.rapport = self.lire_dans(self.prepare, 'amorcage.json')
        preuve_valide(self.rapport, self.preuve, self.candidat)
        self.resume = self.lire_dans(self.prepare, 'evaluation-privee.json')
        preparer.verifier_resume(self.resume, self.candidat, self.rapport['paquet'])
        exiger(self.resume['systeme_amorcage'] == self.rapport['systeme_amorcage'] and
            str((self.prepare/'generation-amorcage').resolve()) == self.rapport['systeme_amorcage'],
            'Génération préparée différente')
        self.ancien = self.rapport['systeme_actif']; self.nouveau = self.rapport['systeme_amorcage']
        self.outils = Path(self.ancien) / 'sw/bin'
        self.worker = 'vision-amorcage-essai-' + revision[:12]
        self.retour = 'vision-amorcage-retour-' + revision[:12]
        self.py = str(Path(sys.executable).resolve())

    @staticmethod
    def lire_dans(d, nom):
        fd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: return json.loads(identite.lire(fd, nom))
        finally: os.close(fd)

    def lire(self, nom): return json.loads(identite.lire(self.fd, nom))
    def ecrire(self, nom, valeur): identite.ecrire(self.fd, nom, valeur)
    def sauver(self, nom, valeur): self.ecrire(nom, json.dumps(valeur, ensure_ascii=False))
    def marque(self, nom):
        try: identite.lire(self.fd, nom, 0); return True
        except FileNotFoundError: return False

    def commande(self, *args, timeout=240):
        return construction.commande(*args, timeout=timeout)

    def verifier_pid(self):
        return {s: int(self.commande(self.outils/'systemctl', 'show', s, '--property=MainPID', '--value').strip()) for s in SERVICES}

    def empreinte_entree(self):
        p = Path('/etc/nixos/configuration.nix')
        return hashlib.sha256((os.readlink(p).encode() if p.is_symlink() else b'') + p.read_bytes()).hexdigest()

    def preparer(self):
        exiger(not (self.d/'plan.json').exists() and not self.marque('commence'), 'Essai déjà préparé ou engagé')
        etape('socle_avant_essai'); construction.verifier_socle(self.candidat)
        exiger(not self.commande(self.outils/'ss', '-Hltpn', 'sport = :8085').strip(), 'Port d’identité déjà occupé')
        exiger(not Path('/var/lib/mrjam-amorcage-postgresql').exists() and
            not Path('/run/mrjam-amorcage-postgresql').exists(), 'Cluster réservé déjà présent : audit requis')
        etape('import_prive_verifie')
        destination = preparer.composants.initial.DESTINATION
        identite.preparer(ROOT/'operations/identite/realm.json', destination, destination/'proton-smtp.json', controler=True)
        secretfd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            secret_amorcage(secretfd)
        finally: os.close(secretfd)
        etape('entree_reversible')
        self.commande(self.outils/'nix-store', '--add-root', self.d/'ancienne-generation', '--realise', self.ancien)
        original = Path('/etc/nixos/configuration.nix').resolve()
        shutil.copy2('/etc/nixos/configuration.nix', self.d/'configuration-avant.nix', follow_symlinks=False)
        self.ecrire('entree.nix', entree_nix(original, self.prepare/'source/modules/identite-amorcage.nix', self.candidat['audit']['fournisseur']))
        systeme = json.loads(self.commande('nix-instantiate', '--eval', '--strict', '--json',
            ROOT/'scripts/vision-identite-amorcage-systeme.nix', '--argstr', 'configuration', self.d/'entree.nix',
            '-I', 'nixpkgs='+self.candidat['audit']['nixpkgs']))
        exiger(systeme == self.nouveau, 'Entrée persistante ne reproduisant pas la construction')
        etape('dry_activate')
        r = subprocess.run([self.nouveau+'/bin/switch-to-configuration', 'dry-activate'],
            capture_output=True, timeout=120)
        texte = (r.stdout+r.stderr).decode(); self.ecrire('dry-activate-prive.txt', texte)
        exiger(r.returncode == 0, 'Dry-activate refusé'); verifier_dry(texte)
        construction.verifier_socle(self.candidat)
        etape('copie_locale_chiffree')
        fd = identite.ouvrir_prive(self.fd, 'vision-avant.dump.age', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, 'wb') as out:
            r = subprocess.run([str(self.outils/'vision-backup')], stdout=out, stderr=subprocess.PIPE, timeout=120)
            out.flush(); os.fsync(out.fileno())
        exiger(r.returncode == 0, 'Copie locale Vision refusée')
        with (self.d/'vision-avant.dump.age').open('rb') as f:
            exiger(f.read(22) == b'age-encryption.org/v1\n', 'Copie locale non chiffrée')
        self.ecrire('retour.sh', script_retour(self.d, self.ancien, self.ancien, self.outils, worker=self.worker+'.service'))
        os.chmod(self.d/'retour.sh', 0o700)
        self.commande(self.outils/'bash', '-n', self.d/'retour.sh')
        self.ecrire('finalisation.lock', '')
        etape('repetition_timer')
        self.commande(self.outils/'systemd-run', '--unit=vision-amorcage-repetition-'+self.revision[:12],
            '--on-active=3s', '--timer-property=AccuracySec=1s', '--property=UMask=0077', '--collect', self.outils/'touch', self.d/'timer-repete')
        limite = time.monotonic()+20
        while not (self.d/'timer-repete').exists() and time.monotonic()<limite: time.sleep(1)
        exiger(self.marque('timer-repete'), 'Timer indépendant non exécuté')
        pids = self.verifier_pid(); exiger(all(p>0 for p in pids.values()), 'Service essentiel absent')
        self.sauver('plan.json', dict(ancien=self.ancien, nouveau=self.nouveau,
            pids=pids, entree_empreinte=self.empreinte_entree(),
            programme_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            timer_repete=True, copie_locale_chiffree=True))
        print(json.dumps({'plan_verifie': True, 'timer_repete': True, 'activation': False}), flush=True)

    def demarrer(self):
        plan = self.lire('plan.json')
        exiger(not self.marque('commence') and self.marque('timer-repete') and
            plan['programme_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Plan absent ou déjà engagé')
        construction.verifier_socle(self.candidat)
        exiger(self.verifier_pid() == plan['pids'] and self.empreinte_entree() == plan['entree_empreinte'], 'Socle changé depuis le plan')
        self.commande(self.outils/'systemd-run', '--unit='+self.retour, '--on-active=15min',
            '--timer-property=AccuracySec=1s', '--property=Type=oneshot', '--property=TimeoutStartSec=6min', self.d/'retour.sh')
        self.commande(self.outils/'systemctl', 'is-active', self.retour+'.timer')
        self.ecrire('commence', '')
        self.commande(self.outils/'systemd-run', '--unit='+self.worker, '--property=Type=exec',
            '--property=TimeoutStopSec=45s', '--property=RuntimeMaxSec=10min', '--property=UMask=0077',
            '--property=StandardOutput=append:'+str(self.d/'worker-prive.log'),
            '--property=StandardError=append:'+str(self.d/'worker-prive.log'),
            '--setenv=PATH='+str(self.outils)+':/run/wrappers/bin',
            '--setenv=NIX_PATH=nixpkgs='+self.candidat['audit']['nixpkgs'],
            self.py, Path(__file__), self.revision, 'worker')
        print(json.dumps({'retour_autonome_arme': True, 'essai_lance': True}), flush=True)

    def verifier_local(self, enregistre=False):
        exiger(not self.marque('retour-commence'), 'Retour commencé')
        exiger(str(Path('/run/current-system').resolve()) == self.nouveau and
            str(Path('/nix/var/nix/profiles/system').resolve()) == (self.nouveau if enregistre else self.ancien), 'Génération inattendue')
        plan = self.lire('plan.json')
        exiger(self.verifier_pid() == plan['pids'], 'Service essentiel redémarré')
        for nom, unite in self.resume['unites_essentielles'].items():
            exiger(str(Path('/etc/systemd/system/'+nom+'.service').resolve().parent) == unite, 'Unité essentielle différente')
        exiger(str(Path('/srv/vision/current').resolve()) == self.candidat['audit']['vision'] and
            construction.preparation.socle.source_fournisseur_active() == self.candidat['audit']['fournisseur'], 'Vision ou fournisseur changé')
        self.commande(self.outils/'systemctl', 'is-active', 'sshd', 'nginx', 'postgresql', 'vision', 'matheval', 'mrj-auth',
            'mrjam-amorcage-postgresql', 'mrjam-amorcage-identite', 'mrjam-amorcage-sauvegarde.timer')
        for nom, valeurs in {'mrjam-amorcage-identite': {'DynamicUser': 'yes', 'User': 'keycloak', 'NoNewPrivileges': 'yes'},
                'mrjam-amorcage-postgresql': {'User': 'postgres', 'NoNewPrivileges': 'yes'}}.items():
            for cle, valeur in valeurs.items():
                exiger(self.commande(self.outils/'systemctl', 'show', nom, '--property='+cle, '--value').strip() == valeur,
                    'Confinement systemd différent')
        pid = int(self.commande(self.outils/'systemctl', 'show', 'mrjam-amorcage-identite', '--property=MainPID', '--value'))
        ligne = next(l for l in Path('/proc/'+str(pid)+'/status').read_text().splitlines() if l.startswith('Uid:'))
        exiger(all(int(x)>0 for x in ligne.split()[1:]), 'Identité lancée avec privilèges root')
        ecoutes = self.commande(self.outils/'ss', '-Hltpn', 'sport = :8085').splitlines()
        exiger(len(ecoutes)==1 and ecoutes[0].split()[3]=='127.0.0.1:8085', 'Identité exposée hors boucle locale')
        pg = Path(self.resume['postgres_paquet'])/'bin/psql'; socket = '/run/mrjam-amorcage-postgresql'
        env = {k:v for k,v in os.environ.items() if not k.startswith('PG')}; env['PGCONNECT_TIMEOUT']='5'
        sql = "SELECT json_build_object('tcp',current_setting('listen_addresses'),'socket',current_setting('unix_socket_directories'),'data',current_setting('data_directory'),'encodage',current_setting('server_encoding'),'majeure',current_setting('server_version_num')::int/10000,'role',(SELECT json_build_object('login',rolcanlogin,'super',rolsuper,'base',rolcreatedb,'role',rolcreaterole,'replication',rolreplication,'bypass',rolbypassrls,'heritage',rolinherit,'sans_mdp',rolpassword IS NULL) FROM pg_authid WHERE rolname='keycloak'),'groupes',(SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='keycloak')));"
        r = subprocess.run([str(self.outils/'runuser'), '-u', 'postgres', '--', str(pg), '-XAtq', '-v', 'ON_ERROR_STOP=1',
            '-h', socket, '-U', 'postgres', '-d', 'mrjam_identite', '-c', sql], env=env, capture_output=True, timeout=15)
        exiger(r.returncode == 0, 'Cluster privé indisponible'); resultat = json.loads(r.stdout)
        exiger(resultat == dict(tcp='', socket=socket, data='/var/lib/mrjam-amorcage-postgresql', encodage='UTF8', majeure=17,
            role=dict(login=True, super=False, base=False, role=False, replication=False, bypass=False, heritage=False, sans_mdp=True), groupes=0),
            'Paramètres du cluster privé différents')
        r = subprocess.run([str(pg), '-XAtq', '-h', socket, '-U', 'keycloak', '-d', 'mrjam_identite', '-c', 'SELECT 1;'],
            env=env, capture_output=True, timeout=10)
        exiger(r.returncode != 0 and b'peer' in r.stderr.lower(), 'Autre UID non refusé par peer')
        destination = preparer.composants.initial.DESTINATION
        fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            secret = identite.lire(fd, 'amorcage-admin.secret', 128).strip()
            realm = json.loads(identite.lire(fd, 'mrjam-realm.json'))
        finally: os.close(fd)
        return controle.verifier(secret, realm)

    def worker(self):
        try:
            exiger(self.marque('commence') and not self.marque('enregistre'), 'Essai non engagé')
            self.commande(self.outils/'systemctl', 'is-active', self.retour+'.timer')
            construction.verifier_socle(self.candidat)
            etape('essai_generation'); self.commande(self.nouveau+'/bin/switch-to-configuration', 'test', timeout=360)
            etape('controles_locaux'); controles = self.verifier_local()
            etape('copie_identite_chiffree')
            self.commande(self.outils/'systemctl', 'start', 'mrjam-amorcage-sauvegarde', timeout=120)
            exiger(self.commande(self.outils/'systemctl', 'show', 'mrjam-amorcage-sauvegarde', '--property=Result', '--value').strip() == 'success', 'Copie d’identité refusée')
            copies = list(Path('/var/backup/mrjam-amorcage').glob('*.age'))
            exiger(copies, 'Copie d’identité absente')
            for p in copies:
                exiger(not p.is_symlink() and p.stat().st_uid==0 and stat.S_IMODE(p.stat().st_mode)==0o600, 'Copie non privée')
                with p.open('rb') as f: exiger(f.read(22)==b'age-encryption.org/v1\n', 'Copie non chiffrée')
            self.verifier_local(); self.sauver('tests-locaux.json', controles)
            self.ecrire('teste', '')
        except Exception:
            if not self.marque('echec'): self.ecrire('echec', '')
            raise

    def attendre(self):
        limite = time.monotonic()+600
        while time.monotonic()<limite:
            exiger(not any(self.marque(n) for n in ('echec', 'retour-commence', 'retour-termine')), 'Essai interrompu')
            if self.marque('teste'):
                print(json.dumps({'controles_locaux': True, 'retour_autonome_arme': True})); return
            time.sleep(5)
        raise ValueError('Délai d’essai dépassé')

    def finaliser(self):
        fd = identite.ouvrir_prive(self.fd, 'finalisation.lock', os.O_RDWR, maximum=0)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            exiger(self.marque('teste') and not any(self.marque(n) for n in ('echec','retour-commence','retour-termine','enregistre')),
                'Enregistrement interdit après retour ou échec')
            self.commande(self.outils/'systemctl', 'is-active', self.retour+'.timer')
            self.verifier_local()
            exiger(self.empreinte_entree()==self.lire('plan.json')['entree_empreinte'], 'Entrée originale modifiée')
            temp = Path('/etc/nixos/configuration.nix.amorcage')
            exiger(not temp.exists() and not temp.is_symlink(), 'Entrée temporaire déjà présente')
            temp.symlink_to(self.d/'entree.nix'); os.replace(temp, '/etc/nixos/configuration.nix')
            self.commande(self.outils/'nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', self.nouveau)
            self.commande(self.nouveau+'/bin/switch-to-configuration', 'boot')
            self.verifier_local(enregistre=True)
            rapport = dict(version=1, infrastructure=self.revision, preparation=self.preuve['infrastructure'],
                systeme_ancien=self.ancien, systeme_amorcage=self.nouveau, vision=self.candidat['vision'],
                style=self.candidat['style'], activation_reservee=True, generation_enregistree=True,
                retour_autonome=True, retour_neutralise=True, copie_locale_chiffree=True,
                postgres_prive=True, services_conserves=True, identite_humaine=False, mode_vision_oidc=False, inscriptions=False)
            self.sauver('activation.json', rapport)
            self.ecrire('enregistre', '')
        finally: os.close(fd)
        # Le marqueur durable empêche désormais le timer d'annuler cet essai.
        subprocess.run([str(self.outils/'systemctl'), 'stop', self.retour+'.timer'], capture_output=True, timeout=20)
        print(json.dumps(rapport), flush=True)

    def retourner(self):
        if self.marque('enregistre'):
            print(json.dumps({'retour': 'enregistrement_deja_termine'})); return
        if not self.marque('commence'):
            subprocess.run([str(self.outils/'systemctl'), 'stop', self.retour+'.timer'], capture_output=True, timeout=20)
            construction.verifier_socle(self.candidat); return
        self.commande(self.outils/'systemctl', 'start', self.retour+'.service', timeout=360)
        exiger(self.marque('retour-termine'), 'Retour non terminé')
        subprocess.run([str(self.outils/'systemctl'), 'stop', self.retour+'.timer'], capture_output=True, timeout=20)
        construction.verifier_socle(self.candidat)
        print(json.dumps({'retour_termine': True, 'socle_retabli': True, 'inscriptions': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('revision'); p.add_argument('action', choices=('preparer','demarrer','worker','attendre','finaliser','retourner'))
    a = p.parse_args(); essai = None
    try:
        essai = Essai(a.revision); getattr(essai, a.action)()
    except Exception:
        try: construction.preparation.diagnostic_prive(traceback.format_exc().encode())
        except Exception: pass
        print(json.dumps({'essai': 'interrompu', 'etape': ETAPE, 'donnees_affichees': False}), file=sys.stderr)
        sys.exit(1)
    finally:
        if essai is not None: os.close(essai.fd)
