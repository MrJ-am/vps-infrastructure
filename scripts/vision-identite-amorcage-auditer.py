"""Diagnostic du seul essai identifié ; jamais d'extrait privé dans la sortie."""
import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import pwd
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ETAPE = 'demarrage'
REVISION = '88dc20580cbfc3e790eb19f366794b8b94f87e9d'
DERNIERE = 'f9dae92a39f350d5aa5b5795f74b04f6827d60ff'
DOSSIER = Path('/root/vision-identite-amorcage-essais')/REVISION
EMPREINTES = {
    'vision-identite-amorcage-activer.py':'c6f9871bc0d8a7db4ccf85627317b098b3137f0df978cb538f360d803f21cb66',
    'vision-identite-construire.py':'59b622d13d06994f203bfaf570d142ab214aed6ea3c62ca0d92141ecba6843c5',
    'vision-multiutilisateur-preparer.py':'79bc15f3bbd242e29aa1f9321d90adf35145adeeec28e77c833c3a3c255143d3',
}
SCRIPTS = tuple(EMPREINTES)
UNITES = frozenset(('sshd.service', 'nginx.service', 'postgresql.service', 'vision.service',
    'acme-log.mrj.am.service',
    'matheval.service', 'mrj-auth.service', 'nginx-config-reload.service', 'nginx-validate-config.service',
    'systemd-journald.service', 'systemd-journald@identite.service', 'systemd-journald@http.service',
    'systemd-journald@identite.socket', 'systemd-journald-varlink@identite.socket',
    'mrjam-amorcage-postgresql.service', 'mrjam-amorcage-identite.service',
    'mrjam-amorcage-sauvegarde.service', 'mrjam-amorcage-sauvegarde.timer',
    'nix-daemon.service', 'nscd.service', 'systemd-logind.service', 'dbus.service', 'polkit.service',
    'systemd-tmpfiles-setup.service', 'systemd-tmpfiles-resetup.service', 'systemd-sysctl.service',
    'systemd-udevd.service', 'logrotate.service', 'user@0.service', 'user-runtime-dir@0.service'))
MOTIFS = {
    'dry_refuse': r'(?:RuntimeError|ConstructionRefusee): Dry-activate refusé',
    'dry_incomplet': r'(?:RuntimeError|ConstructionRefusee): Dry-activate absent ou incomplet',
    'interruption_socle': r'(?:RuntimeError|ConstructionRefusee): Interruption du socle annoncée',
    'unite_etrangere': r'(?:RuntimeError|ConstructionRefusee): Dry-activate annonce une unité étrangère',
    'permission_refusee': r'Permission denied',
    'systemd_indisponible': r'Failed to connect to (?:system|bus)|System has not been booted with systemd',
    'activation_script_refuse': r'activation script failed|failed to run activation script',
    'lancement_python_refuse': r'Failed at step EXEC|status=203/EXEC|Failed to (?:execute|locate executable)|Exec format error',
    'bibliotheque_python_absente': r'ModuleNotFoundError:',
    'source_operateur_differente': r'(?:RuntimeError|ConstructionRefusee): Source opérateur différente',
    'commande_timeout': r'(?:RuntimeError|ConstructionRefusee): Délai de construction ou de contrôle dépassé',
    'commande_refusee': r'(?:RuntimeError|ConstructionRefusee): Commande de construction ou de contrôle refusée',
    'essai_timeout': r'ValueError: Délai d’essai dépassé',
    'action_masquee': r"getattr\(essai, a\.action\)\(\)[\s\S]{0,1024}TypeError: 'str' object is not callable",
    'nixpkgs_introuvable': r"file 'nixpkgs' was not found|cannot find.*nixpkgs",
    'journal_pg_peer_refuse': r'peer authentication failed',
    'journal_pg_initialisation_refusee': r'initdb: error:',
    'journal_pg_proprietaire_incorrect': r'(?:data directory.*wrong ownership|must be owned by)',
    'journal_db_absente': r'database "mrjam_identite" does not exist',
    'journal_role_absent': r'role "keycloak" does not exist',
    'journal_memoire': r'out of memory|OutOfMemoryError|oom-kill',
    'unite_pg_echec': r'Failed to start.*mrjam-amorcage-postgresql|mrjam-amorcage-postgresql\.service:.*(?:Failed|failed|status=[1-9])',
    'unite_identite_echec': r'Failed to start.*mrjam-amorcage-identite|mrjam-amorcage-identite\.service:.*(?:Failed|failed|status=[1-9])',
    'dependance_identite_refusee': r'Dependency failed.*amorcage|Job mrjam-amorcage-identite\.service/start failed with result .dependency',
    'outil_shell_absent': r'(?:id|ls|cat|chmod|find|bash|pg_ctl|initdb|psql): (?:command not found|not found)',
    'pg_memoire_partagee': r'could not (?:map dynamic|open|create) shared memory',
    'pg_configuration_inaccessible': r'could not (?:open|access) (?:file|configuration file)',
    'jdbc_connexion_refusee': r'Unable to obtain isolated JDBC connection|Failed to obtain JDBC connection|org\.postgresql\.util\.PSQLException',
    'keycloak_echec_demarrage': r'Failed to start server in \(production\) mode|ERROR: Failed to start server',
    'credential_indisponible': r'Failed to (?:load|set up) credentials|Failed at step CREDENTIALS',
}
ETAPES = frozenset(('demarrage', 'essai_generation', 'controles_locaux', 'copie_identite_chiffree'))
EXCEPTIONS = frozenset(('IOException','FileNotFoundException','NoSuchFileException','AccessDeniedException',
    'IllegalArgumentException','IllegalStateException','ClassNotFoundException','NoClassDefFoundError',
    'UnsatisfiedLinkError','OutOfMemoryError','PSQLException','SQLException','PersistenceException',
    'LiquibaseException','DatabaseException','ExecutionException','SecurityException','TimeoutException','CompletionException'))
ETAPES_SYSTEMD = frozenset(('EXEC','USER','GROUP','CHDIR','CREDENTIALS','NAMESPACE','RUNTIME_DIRECTORY',
    'STATE_DIRECTORY','LOGS_DIRECTORY','CACHE_DIRECTORY','STDOUT','STDERR','CAPABILITIES'))
MOTIFS_NGINX = {
    'directive_dupliquee': r'"[^"\n]+" directive is duplicate',
    'directive_inconnue': r'unknown directive "',
    'directive_contexte': r'directive is not allowed here',
    'variable_inconnue': r'unknown "[^"\n]+" variable',
    'syntaxe': r'unexpected "|unexpected end of file|invalid number of arguments|invalid parameter',
    'certificat_inaccessible': r'cannot load certificate\b',
    'cle_inaccessible': r'cannot load certificate key\b',
    'cle_certificat_differents': r'key values mismatch',
    'configuration_tls': r'SSL_CTX_|PEM_read_bio|BIO_new_file',
    'zone_sans_taille': r'zero size shared memory zone',
    'zone_dupliquee': r'zone "[^"\n]+" is already bound',
    'port_occupe': r'bind\(\).*Address already in use',
    'permission_refusee': r'Permission denied',
    'fichier_absent': r'No such file or directory',
    'configuration_refusee': r'configuration file .* test failed',
    'parametre_invalide': r'invalid parameter',
    'nombre_arguments': r'invalid number of arguments',
    'fin_fichier': r'unexpected end of file',
    'jeton_inattendu': r'unexpected "',
    'parametre_syslog': r'(?:invalid|unknown) syslog parameter|syslog.*invalid parameter',
    'socket_syslog': r'(?:connect|send).*syslog.*failed|syslog.*(?:connect|send).*failed',
}
DIRECTIVES_NGINX = frozenset(('client_max_body_size','proxy_pass','proxy_set_header','add_header',
    'limit_req','limit_req_zone','limit_conn','limit_conn_zone','ssl_certificate','ssl_certificate_key',
    'listen','location','server','server_name','access_log','error_log','return','include','pid',
    'log_format','default_type','types','ssl_trusted_certificate'))
DESTINATAIRE_DIAGNOSTIC = 'age19tndze9vpljjvkljzxw0wj2zje5vjg0jh4e8npm82jkt65gs9vpsw5909d'


def erreurs_demarrage_nginx(texte):
    lignes=[l for l in texte.splitlines() if l.startswith('nginx: [emerg]')]
    contenu='\n'.join(lignes[:16]).encode()
    if len(contenu)>16384:raise ValueError('Diagnostic technique trop grand')
    return contenu


def chiffrer_erreurs_nginx(texte):
    try:contenu=erreurs_demarrage_nginx(texte)
    except ValueError:return dict(disponible=False)
    if not contenu:return dict(disponible=True,lignes=0)
    try:
        r=subprocess.run(['age','-a','-r',DESTINATAIRE_DIAGNOSTIC],input=contenu,capture_output=True,timeout=10)
        if r.returncode or len(r.stdout)>32768 or not r.stdout.startswith(b'-----BEGIN AGE ENCRYPTED FILE-----\n'):
            return dict(disponible=False)
        return dict(disponible=True,lignes=len(contenu.splitlines()),age_base64=base64.b64encode(r.stdout).decode())
    except (OSError,subprocess.TimeoutExpired):return dict(disponible=False)


def ligne_configuration_nginx(chemin, numero):
    if not re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-nginx\.conf',chemin) or not 1<=numero<=200000:
        return dict(disponible=False)
    try:
        fd=os.open(chemin,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_nlink!=1 or s.st_mode&0o022 or s.st_size>1048576:
                return dict(disponible=False)
            lignes=os.read(fd,1048577).decode(errors='replace').splitlines()
            if numero>len(lignes):return dict(disponible=False)
            premier=re.match(r'\s*([a-z_]+)\b',lignes[numero-1])
            directive=premier.group(1) if premier and premier.group(1) in DIRECTIVES_NGINX else None
            return dict(disponible=True,ligne=numero,directive=directive,
                droits=stat.S_IMODE(s.st_mode),lecture_autres=bool(s.st_mode&0o004))
        finally:os.close(fd)
    except OSError:return dict(disponible=False)


def references_nginx(texte):
    configurations=[]
    for chemin,numero in sorted(set(re.findall(r'\bin (/[^\s:\n]+):([0-9]{1,6})',texte)))[:16]:
        configurations.append(ligne_configuration_nginx(chemin,int(numero)))
    return configurations[:16]


def classer_nginx(texte):
    directives=set(re.findall(r'"([^"\n]+)" directive is (?:duplicate|not allowed here)',texte))
    directives.update(re.findall(r'unknown directive "([^"\n]+)"',texte))
    directives.update(re.findall(r'invalid number of arguments in "([^"\n]+)" directive',texte))
    operations=sorted({n for n in ('open','mkdir','chown','connect','bind','socket','send','read','write') if re.search(r'\b'+n+r'\(\)',texte)})
    chemins=set(re.findall(r'(?:open|mkdir|chown|connect|bind)\(\) "([^"\n]+)"',texte))
    types_chemins=set()
    for p in chemins:
        if p=='/run/systemd/journal.http/syslog':types_chemins.add('socket_journal_http')
        elif p in ('/var/lib/acme/log.mrj.am/fullchain.pem','/var/lib/acme/log.mrj.am/key.pem','/var/lib/acme/log.mrj.am/chain.pem'):types_chemins.add('certificat_log')
        elif re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-nginx\.conf',p):types_chemins.add('configuration_nginx')
        else:types_chemins.add('inconnu')
    return dict(categories=sorted(n for n,m in MOTIFS_NGINX.items() if re.search(m,texte)),
        directives_connues=sorted(directives & DIRECTIVES_NGINX),
        directives_inconnues=len(directives-DIRECTIVES_NGINX),operations=operations,types_chemins=sorted(types_chemins),
        errno=sorted({int(n) for n in re.findall(r'\(([0-9]{1,3}): ',texte) if int(n)<=255}),**sorties(texte))


def journaux_nginx(outils):
    rapports={}
    for namespace in ('http','defaut'):
        try:
            r=subprocess.run([str(outils/'journalctl'),*(['--namespace=http'] if namespace=='http' else []),
                '--unit=nginx.service','--unit=nginx-validate-config.service',
                '--since=2026-10-09 17:05:00 UTC','--until=2026-10-09 17:06:40 UTC',
                '--lines=300','--output=cat','--no-pager'],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):r=None
        disponible=r is not None and r.returncode==0 and len(r.stdout)<=1048576
        texte=r.stdout.decode(errors='replace') if disponible else ''
        rapports[namespace]=dict(disponible=disponible,**classer_nginx(texte),configurations=references_nginx(texte),
            erreurs_demarrage_chiffrees=chiffrer_erreurs_nginx(texte) if namespace=='http' and disponible else dict(disponible=False))
    return rapports


def sorties(texte):
    return dict(codes=sorted({int(n) for n in re.findall(r'status=([0-9]{1,3})(?:/|,|\s)',texte) if int(n)<=255}),
        etapes_systemd=sorted({e for e in ETAPES_SYSTEMD if re.search(r'Failed at step '+e+r'\b',texte)}),
        exceptions=sorted({e for e in EXCEPTIONS if re.search(r'(?<![A-Za-z0-9_])'+e+r'\b',texte)}))


def classer(diagnostic, dry):
    unites = {}
    for action, noms in re.findall(r'would (stop|restart|reload) the following units: ([^\n]+)', dry):
        valeurs = {v.strip() for v in noms.split(',')}
        connues = valeurs & UNITES
        acme = {v for v in valeurs if re.fullmatch(r'acme-[A-Za-z0-9_.@-]+\.(?:service|timer|target)', v)}
        unites[action] = dict(connues=sorted(connues), acme=len(acme), inconnues=len(valeurs-connues-acme))
    echecs=set()
    for noms in re.findall(r'warning: the following units failed: ([^\n]+)',diagnostic):
        echecs.update(n.strip() for n in noms.split(','))
    echecs.update(re.findall(r'Failed to (?:start|restart|reload) ([A-Za-z0-9_.@-]+\.(?:service|socket|timer|target))',diagnostic))
    return dict(categories=[nom for nom,motif in MOTIFS.items() if re.search(motif, diagnostic+'\n'+dry)],
        activation_annoncee='would activate the configuration' in dry,
        redemarrage_systemd='would restart systemd' in dry,
        arret_swap='would stop swap' in dry, unites=unites,
        unites_echec=dict(bilan_present=bool(echecs),connues=sorted(echecs&UNITES),inconnues=len(echecs-UNITES)))


def lire(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1 or s.st_size > 262144:
            raise ValueError('Fichier privé requis')
        contenu = os.read(fd, 262145)
        if len(contenu) > 262144: raise ValueError('Journal trop grand')
        return contenu.decode('utf-8', errors='replace')
    finally: os.close(fd)


def verifier_retour(marqueurs):
    if not all(marqueurs.get(n) is True for n in ('commence','plan.json','retour-commence','retour-termine')) or marqueurs.get('enregistre') is not False:
        raise ValueError('Tentative non retournée : aucune lecture de diagnostic')


def classer_worker(texte):
    etapes = re.findall(r'\{"etape": "([a-z_]+)"\}', texte)
    return dict(etapes=[e for e in etapes if e in ETAPES], **classer(texte, ''))


def verifier_reprise(rapport):
    if (not isinstance(rapport,dict) or rapport.get('revision') != REVISION or
        not all(rapport.get(k) is True for k in ('socle_conserve','retour_termine')) or
        not all(rapport.get(k) is False for k in ('generation_enregistree','activation','inscriptions','cluster_prive_present')) or
        set(rapport.get('categories',[])) != {'action_masquee','essai_timeout'} or
        rapport.get('worker',{}).get('etat') not in ('inactive','failed') or
        rapport.get('controle_worker',{}).get('etapes') != [] or
        rapport.get('controle_worker',{}).get('categories') != []):
        raise ValueError('Cause ou état différents : reprise du worker interdite')


def cadres(texte, source):
    source=Path(source);s=source.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o700:
        raise ValueError('Source hors dossier privé')
    connus={}
    for nom in SCRIPTS:
        p=Path(source)/'scripts'/nom
        if not p.exists(): continue
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_nlink!=1 or s.st_mode&0o002 or s.st_size>131072:
                raise ValueError('Source de diagnostic non conforme')
            contenu=os.read(fd,131073)
            if hashlib.sha256(contenu).hexdigest()!=EMPREINTES[nom]:raise ValueError('Source historique différente')
            code=contenu.decode()
        finally:os.close(fd)
        arbre=ast.parse(code);fonctions={'<module>':[(1,len(code.splitlines()))]}
        for n in ast.walk(arbre):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                fonctions.setdefault(n.name,[]).append((n.lineno,n.end_lineno))
        connus[str(p)]=(nom,fonctions)
    resultat=[]
    for chemin,ligne,fonction in re.findall(r'File "([^"\n]+)", line ([0-9]{1,6}), in ([A-Za-z0-9_]+|<module>)',texte):
        if chemin not in connus:continue
        nom,fonctions=connus[chemin];numero=int(ligne)
        if any(debut<=numero<=fin for debut,fin in fonctions.get(fonction,[])):
            resultat.append(dict(script=nom,fonction=fonction,ligne=numero))
    return resultat[-16:]


def etat_worker(outils, revision=REVISION):
    if revision not in (REVISION,DERNIERE):raise ValueError('Tentative non qualifiée')
    unite = 'vision-amorcage-essai-' + revision[:12] + '.service'
    r = subprocess.run([str(outils/'systemctl'),'show',unite,'--property=ActiveState',
        '--property=ExecMainStatus'], capture_output=True, timeout=5)
    valeurs = dict(l.split('=',1) for l in r.stdout.decode().splitlines() if '=' in l)
    if r.returncode or valeurs.get('ActiveState') not in ('inactive','failed') or not re.fullmatch(r'[0-9]{1,3}',valeurs.get('ExecMainStatus','')) or int(valeurs['ExecMainStatus']) > 255:
        raise ValueError('Worker non arrêté ou état indéterminé')
    journal = subprocess.run([str(outils/'journalctl'),'--unit='+unite,'--lines=120',
        '--output=cat','--no-pager'], capture_output=True, timeout=10)
    if journal.returncode or len(journal.stdout)>1048576: raise ValueError('Journal technique indisponible')
    return dict(etat=valeurs['ActiveState'], code=int(valeurs['ExecMainStatus'])), journal.stdout.decode(errors='replace')


def unites_identite(outils):
    rapports={}
    for nom in ('mrjam-amorcage-postgresql','mrjam-amorcage-identite','mrjam-amorcage-sauvegarde'):
        try:
            r=subprocess.run([str(outils/'systemctl'),'show',nom+'.service',
                '--property=ActiveState','--property=ExecMainStatus','--property=Result'],capture_output=True,timeout=5)
        except (OSError,subprocess.TimeoutExpired):r=None
        v={} if r is None or len(r.stdout)>65536 else dict(l.split('=',1) for l in r.stdout.decode(errors='replace').splitlines() if '=' in l)
        etat=v.get('ActiveState');code=v.get('ExecMainStatus','')
        disponible=(r is not None and r.returncode==0 and etat in ('active','inactive','failed','activating','deactivating') and
            re.fullmatch(r'[0-9]{1,3}',code) is not None and int(code)<=255)
        resultats=('success','exit-code','signal','timeout','oom-kill','resources','protocol','start-limit-hit')
        resultat=v.get('Result');resultat=resultat if disponible and resultat in resultats else 'indetermine'
        journaux={};categories=set();textes=[]
        for namespace in ('identite','defaut'):
            try:
                j=subprocess.run([str(outils/'journalctl'),*(['--namespace=identite'] if namespace=='identite' else []),
                    '--unit='+nom+'.service','--lines=160','--output=cat','--no-pager'],capture_output=True,timeout=10)
            except (OSError,subprocess.TimeoutExpired):j=None
            disponible_j=j is not None and j.returncode==0 and len(j.stdout)<=1048576
            journaux[namespace]=disponible_j
            if disponible_j:
                texte=j.stdout.decode(errors='replace');textes.append(texte);categories.update(classer(texte,'')['categories'])
        rapports[nom]=dict(etat=etat if disponible else 'indetermine',code=int(code) if disponible else None,
            resultat=resultat,etat_disponible=disponible,journal_disponible=all(journaux.values()),
            journaux_disponibles=journaux,categories=sorted(categories),**sorties('\n'.join(textes)))
    return rapports


def namespace_identite(outils):
    try:
        r=subprocess.run([str(outils/'journalctl'),'--namespace=identite','--lines=300',
            '--output=cat','--no-pager'],capture_output=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):return dict(disponible=False)
    if r.returncode or len(r.stdout)>1048576:return dict(disponible=False)
    texte=r.stdout.decode(errors='replace')
    return dict(disponible=True,categories=classer(texte,'')['categories'],**sorties(texte))


def import_prive():
    destination=Path('/var/lib/mrjam-identite')
    spec=importlib.util.spec_from_file_location('identite_import',ROOT/'scripts/identite-preparer.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    try:
        m.preparer(ROOT/'operations/identite/realm.json',destination,destination/'proton-smtp.json',controler=True)
        secret=lire(destination/'amorcage-admin.secret')
        return dict(import_verifie=True,secret_amorcage_format_verifie=re.fullmatch(r'[A-Za-z0-9_-]{43}\n',secret) is not None)
    except (OSError,ValueError,KeyError):return dict(import_verifie=False,secret_amorcage_format_verifie=False)


def lire_pg(p,uid):
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=uid or s.st_nlink!=1 or s.st_mode&0o077 or s.st_size>262144:
            raise ValueError('Fichier PostgreSQL privé requis')
        return os.read(fd,262145).decode(errors='replace')
    finally:os.close(fd)


def cluster_arrete(paquet):
    d=Path('/var/lib/mrjam-amorcage-postgresql')
    if not d.exists():return dict(present=False)
    uid=pwd.getpwnam('postgres').pw_uid;s=d.lstat()
    prive=stat.S_ISDIR(s.st_mode) and s.st_uid==uid and stat.S_IMODE(s.st_mode)==0o700
    r=dict(present=True,dossier_prive=prive,version17=False,controle_disponible=False,
        etat='indetermine',pid_present=(d/'postmaster.pid').exists(),
        socket_present=Path('/run/mrjam-amorcage-postgresql').exists(),journal_disponible=False,categories=[])
    if not prive:return r
    try:r['version17']=lire_pg(d/'PG_VERSION',uid)=='17\n'
    except (OSError,ValueError):pass
    try:
        texte=lire_pg(d/'serveur-prive.log',uid);r['categories']=classer(texte,'')['categories'];r['journal_disponible']=True
    except (OSError,ValueError):pass
    if not r['version17'] or r['pid_present'] or r['socket_present']:return r
    if not re.fullmatch(r'/nix/store/[0-9a-z]{32}-postgresql-and-plugins-[A-Za-z0-9._+-]+',paquet):
        raise ValueError('Paquet PostgreSQL différent')
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')};env['LC_ALL']='C'
    try:
        c=subprocess.run([paquet+'/bin/pg_controldata','-D',str(d)],capture_output=True,timeout=10,env=env)
        if c.returncode or len(c.stdout)>65536:return r
        etat=re.search(r'(?m)^Database cluster state:\s+([a-z ]+)$',c.stdout.decode(errors='replace'))
        if etat and etat[1] in ('shut down','shut down in recovery','in production','in crash recovery','in archive recovery','shutting down','starting up'):
            r['controle_disponible']=True;r['etat']=etat[1]
    except (OSError,subprocess.TimeoutExpired):pass
    return r


def main(reprise=False):
    global ETAPE
    ETAPE='dossier_prive'
    if os.geteuid() != 0: raise ValueError('Audit root Actions requis')
    revision=REVISION if reprise else DERNIERE
    dossier=DOSSIER if reprise else DOSSIER.parent/DERNIERE
    for path in (dossier.parent, dossier):
        s = path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('Dossier privé requis')
    spec = importlib.util.spec_from_file_location('construction', ROOT/'scripts/vision-identite-construire.py')
    construction = importlib.util.module_from_spec(spec); spec.loader.exec_module(construction)
    candidat = json.loads((ROOT/'operations/vision-multiutilisateur-candidat.json').read_text())
    ETAPE='socle_avant';construction.verifier_socle(candidat)
    ETAPE='retour_durable'
    marqueurs = {nom:(dossier/nom).exists() for nom in ('commence','plan.json','enregistre','retour-commence','retour-termine')}
    verifier_retour(marqueurs)
    for nom,present in marqueurs.items():
        if present: lire(dossier/nom)
    ETAPE='journaux_prives'
    diagnostic = lire(dossier/'diagnostic-prive.log'); dry = lire(dossier/'dry-activate-prive.txt')
    worker = lire(dossier/'worker-prive.log') if (dossier/'worker-prive.log').exists() else ''
    outils=Path(candidat['audit']['systeme'])/'sw/bin'
    ETAPE='worker_arrete';etat,journal = etat_worker(outils,revision)
    details={}
    if not reprise:
        ETAPE='cadres_connus'
        try:details=dict(cadres=cadres(diagnostic,dossier/'source'),cadres_disponibles=True)
        except (OSError,ValueError,SyntaxError,UnicodeError):details=dict(cadres=[],cadres_disponibles=False)
        ETAPE='unites_secondaires';details['unites_identite']=unites_identite(outils)
        ETAPE='namespace_identite';details['journal_namespace_identite']=namespace_identite(outils)
        ETAPE='journaux_nginx';details['journaux_nginx']=journaux_nginx(outils)
        ETAPE='import_prive';details['import_prive']=import_prive()
        ETAPE='cluster_arrete'
        prepare=Path('/root/vision-identite-amorcage-operations/765ce372ccd61ad623e33bf8bb476a5c3be21fba')
        try:
            for chemin in (prepare.parent,prepare):
                s=chemin.lstat()
                if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700:
                    raise ValueError('Préparation privée différente')
            resume=json.loads(lire(prepare/'evaluation-privee.json'))
            details['cluster']=cluster_arrete(resume['postgres_paquet']);details['cluster_disponible']=True
        except (OSError,ValueError,KeyError):details['cluster_disponible']=False
    ETAPE='socle_apres';construction.verifier_socle(candidat)
    rapport = dict(audit_amorcage=3, revision=revision, socle_conserve=True,
        retour_termine=True, generation_enregistree=False, activation=False, inscriptions=False,
        worker=etat, controle_worker=classer_worker(worker+'\n'+journal),
        cluster_prive_present=Path('/var/lib/mrjam-amorcage-postgresql').exists(),
        **classer(diagnostic,dry),**details)
    ETAPE='preuve_reprise'
    if reprise:
        verifier_reprise(rapport); rapport['reprise_worker_autorisee']=True
    print(json.dumps(rapport, ensure_ascii=False))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--reprise-worker',action='store_true');a=p.parse_args()
    try: main(a.reprise_worker)
    except Exception as erreur:
        causes={ValueError:'valeur_refusee',FileNotFoundError:'fichier_absent',PermissionError:'permission_refusee',
            subprocess.TimeoutExpired:'lecture_timeout'}
        print(json.dumps(dict(audit_amorcage=1, diagnostic_refuse=True, activation=False,
            etape=ETAPE,cause=causes.get(type(erreur),'indeterminee'))))
        raise SystemExit(1)
