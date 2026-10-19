"""Ajouter l'adresse publique MCP ; aucun renouvellement forcé ni migration.

Opérations fermées transmises par la CI centrale. Le retour restaure uniquement
la configuration, avec les bases et sessions actuelles, Nextcloud compris.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

NIXPKGS = '/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos'
ENTRY = Path('/etc/nixos/configuration.nix')
PROTECTED = ('sshd', 'nginx', 'postgresql', 'kanidm', 'forgejo',
             'vision-embeddings', 'phpfpm-nextcloud', 'redis-nextcloud')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def run(args, timeout=180):
    p = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        (D/'command-private.log').write_text(p.stdout+'\n'+p.stderr)
        raise RuntimeError('Commande refusée : '+Path(str(args[0])).name)
    return p.stdout.strip()


def write(path, value):
    tmp = path.with_name(path.name+'.new')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


def current():
    return str(Path('/run/current-system').resolve())


def boot():
    return str(Path('/nix/var/nix/profiles/system').resolve())


def pids():
    return {n: run(['systemctl', 'show', n, '-p', 'MainPID', '--value']) for n in PROTECTED}


def unit_state(name):
    p = subprocess.run(['systemctl', 'show', name, '-p', 'LoadState', '-p', 'MainPID'],
                       capture_output=True, text=True, timeout=15)
    values = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
    require(p.returncode == 0 or (p.returncode in (1, 4) and values.get('LoadState') == 'not-found'),
            'État de l’unité transitoire indisponible')
    return values


def stop_if_loaded(name):
    if unit_state(name).get('LoadState') != 'not-found':
        run(['systemctl', 'stop', name])


def systemd_command(name):
    # Une unité transitoire ne reçoit pas le PATH du nix-shell parent.
    # Conserver les chemins d'outils/certificats et le domicile existants,
    # sans transmettre les credentials ni les autres variables du shell.
    names = ('PATH', 'HOME', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NIX_SSL_CERT_FILE')
    require('PATH' in os.environ, 'Chemin des outils absent')
    return ['systemd-run', '--unit='+name]+[
        '--setenv='+key+'='+os.environ[key] for key in names if key in os.environ]


def executable():
    pid = run(['systemctl', 'show', 'mrjam-metier', '-p', 'MainPID', '--value'])
    require(pid.isdigit() and pid != '0', 'Serveur métier arrêté')
    return digest('/proc/'+pid+'/exe'), pid


def lease(state):
    require(current() == boot() == state['base'] and digest(ENTRY) == state['entrySha256'],
            'Configuration modifiée depuis la préparation')


def verify_evaluation(result, target):
    require(result['before'] == target['generation'], 'Génération de référence différente')
    require(result['invariants'] and result['assertions'], 'Configuration hors périmètre')
    require(result['urlBefore'] is None and result['urlAfter'] == target['url'],
            'Adresse MCP avant/après inattendue')
    require(result['changedUnits'] == ['mrjam-metier.service'], 'Autres unités modifiées')


def evaluate(base):
    expr = 'import '+str(D/'payload/evaluation.nix')+' { configuration='+json.dumps(str(base))+'; correction='+json.dumps(str(D/'payload/module.nix'))+'; }'
    return json.loads(run(['nix-instantiate', '-I', 'nixpkgs='+NIXPKGS,
                          '--eval', '--strict', '--json', '--expr', expr], timeout=300))


def prepare():
    require(not (D/'prepared.json').exists(), 'Préparation déjà enregistrée')
    target = json.loads((D/'payload/target.json').read_text())
    require(current() == boot() == target['generation'], 'Production différente de la référence')
    require(executable()[0] == target['artifactSha256'], 'Binaire actif différent')
    original_link = os.readlink(ENTRY) if ENTRY.is_symlink() else None
    base = D/'base.nix'; base.write_bytes(ENTRY.read_bytes())
    result = evaluate(base); verify_evaluation(result, target)
    config = D/'configuration.nix'
    config.write_text('{ imports = [ ./base.nix ./payload/module.nix ]; }\n')
    built = run(['nix-build', '<nixpkgs/nixos>', '-A', 'system', '-I', 'nixpkgs='+NIXPKGS,
                 '-I', 'nixos-config='+str(config), '--no-out-link', '--max-jobs', '1', '--cores', '2'], timeout=1800)
    require(built == result['after'], 'Génération construite différente de l’évaluation')
    for name, path in [('base', target['generation']), ('candidate', built),
                       ('python', str(Path(sys.executable).resolve().parents[1]))]:
        run(['nix-store', '--add-root', str(D/(name+'-root')), '--indirect', '-r', path])
    state = dict(base=target['generation'], generation=built, entrySha256=digest(base),
                 originalLink=original_link, preparedAt=time.time(), target=target)
    lease(state); independent_return(); write(D/'prepared.json', state)
    print(json.dumps(dict(phase='prepared', generation=built, base=state['base'],
                          changedUnits=result['changedUnits'], activated=False)), flush=True)


def clients():
    # Empreintes conservées en mémoire seulement, aucun jeton lu ou imprimé.
    with sqlite3.connect('file:/var/lib/mrjam-metier/log/sessions.sqlite?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        return {hashlib.sha256(json.dumps(r).encode()).hexdigest()
                for r in db.execute('SELECT * FROM log_oauth_clients ORDER BY id')}


def install_entry(content=None, link=None):
    tmp = ENTRY.with_name('.vision-mcp-configuration.nix')
    require(not tmp.exists() and not tmp.is_symlink(), 'Entrée concurrente')
    if link is not None:
        tmp.symlink_to(link)
    else:
        tmp.write_bytes(content); tmp.chmod(0o644)
    tmp.replace(ENTRY)


def own_entry():
    return ('{ imports = [ '+str(D/'configuration.nix')+' ]; }\n').encode()


def rollback():
    state = json.loads((D/'prepared.json').read_text())
    require(current() in (state['base'], state['generation']) and boot() in (state['base'], state['generation']),
            'Génération concurrente, retour refusé')
    require(ENTRY.read_bytes() in (own_entry(), (D/'base.nix').read_bytes()),
            'Configuration concurrente, retour refusé')
    install_entry(content=(D/'base.nix').read_bytes(), link=state['originalLink'])
    run(['nix-env', '-p', '/nix/var/nix/profiles/system', '--set', state['base']])
    run([state['base']+'/bin/switch-to-configuration', 'switch'], timeout=360)
    require(current() == boot() == state['base'], 'Retour non constaté')
    run(['systemctl', 'stop', TIMER+'.timer'])
    write(D/'returned.json', dict(configurationOnly=True, oldDatabaseRestored=False))
    print(json.dumps(dict(phase='returned', oldDatabaseRestored=False)), flush=True)


def independent_return():
    marker = D/'return-witness'; marker.unlink(missing_ok=True)
    worker = TIMER+'-worker'
    run(systemd_command(worker)+['--collect', '/run/current-system/sw/bin/sleep', '60'])
    run(systemd_command(TIMER+'-witness')+['--collect', '--on-active=1s',
         '--timer-property=AccuracySec=1s', sys.executable, __file__, 'witness', REV])
    try:
        for _ in range(75):
            if marker.exists(): break
            time.sleep(.2)
        require(marker.exists(), 'Retour indépendant non exécuté')
        values = unit_state(worker+'.service')
        require(values.get('LoadState') == 'not-found' or values.get('MainPID') == '0',
                'Processus témoin non arrêté')
    finally:
        for unit in (worker+'.service', TIMER+'-witness.timer'):
            stop_if_loaded(unit)


def probe(target):
    deadline = time.monotonic()+30
    while True:
        try:
            with urllib.request.urlopen('https://vision.mrj.am/mcp-config.json', timeout=10) as r:
                config = json.load(r)
                require(r.status == 200 and config['url_mcp'] == target['url'], 'Adresse publiée différente')
            break
        except (urllib.error.URLError, TimeoutError):
            require(time.monotonic() < deadline, 'Configuration MCP indisponible'); time.sleep(.5)
    with urllib.request.urlopen('https://vision.mrj.am/.well-known/oauth-protected-resource/mcp', timeout=20) as r:
        require(r.status == 200 and json.load(r)['resource'] == target['url'], 'Découverte MCP différente')
    with urllib.request.urlopen('https://vision.mrj.am/app.js', timeout=20) as r:
        require(hashlib.sha256(r.read(8*1024*1024)).hexdigest() == target['frontendSha256'], 'Interface différente')
    try:
        urllib.request.urlopen(urllib.request.Request(target['url'], data=b'{}',
            headers={'Content-Type': 'application/json'}), timeout=20)
        raise ValueError('Appel MCP anonyme accepté')
    except urllib.error.HTTPError as e:
        require(e.code == 401, 'Refus MCP anonyme différent')
    return dict(publicConfiguration=True, discovery=True, anonymousDenied=True, frontendUnchanged=True)


def deploy():
    state = json.loads((D/'prepared.json').read_text()); lease(state)
    require(not (D/'deployed.json').exists() and not (D/'returned.json').exists(), 'Opération déjà terminée')
    require(time.time()-state['preparedAt'] < 86400, 'Préparation expirée')
    verify_evaluation(evaluate(D/'base.nix'), state['target'])
    before = pids(); old_binary, old_pid = executable(); registered = clients()
    require(old_binary == state['target']['artifactSha256'], 'Binaire actif différent')
    spec = importlib.util.spec_from_file_location('backup', D/'payload/monolithe-sauvegarde.py')
    backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)
    backup.GENERATION = state['base']
    report = backup.main(REV, sqlite_reprise={'log-native': '/var/lib/mrjam-metier/log/sessions.sqlite'})
    require(report['empreintes_semantiques_identiques'] and report['age_dechiffrement_verifie'], 'Sauvegarde non qualifiée')
    run(['systemctl', 'start', 'mrjam-sauvegarde.service'], timeout=300)
    require(run(['systemctl', 'show', 'mrjam-sauvegarde', '-p', 'Result', '--value']) == 'success', 'Sauvegarde Native refusée')
    independent_return(); lease(state)
    require(pids() == before and executable() == (old_binary, old_pid), 'Service modifié avant activation')
    run(systemd_command(TIMER)+['--on-active=10min', '--timer-property=AccuracySec=1s',
         sys.executable, __file__, 'automatic-return', REV])
    try:
        install_entry(content=own_entry())
        run(['nix-env', '-p', '/nix/var/nix/profiles/system', '--set', state['generation']])
        run([state['generation']+'/bin/switch-to-configuration', 'switch'], timeout=360)
        require(current() == boot() == state['generation'], 'Génération non active')
        require(pids() == before, 'Un service protégé a redémarré')
        binary, pid = executable()
        require(binary == old_binary and pid != old_pid, 'Redémarrage du même binaire non constaté')
        require(registered <= clients(), 'Client OAuth existant perdu')
        run(['systemctl', 'is-active', *PROTECTED, 'mrjam-metier'])
        evidence = probe(state['target'])
        run(['systemctl', 'stop', TIMER+'.timer'])
        evidence.update(revision=REV, generation=current(), artifactSha256=binary,
                        protectedPidsUnchanged=True, oauthClientsPreserved=len(registered),
                        encryptedBackupRestoredInIsolation=True, independentReturnQualified=True,
                        serviceRestarted=True, personalAndroidFlowTested=False)
        write(D/'deployed.json', evidence); print(json.dumps(evidence), flush=True)
    except BaseException:
        rollback(); raise


if __name__ == '__main__':
    os.umask(0o077)
    phase, REV = sys.argv[1:]
    require(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', REV), 'Contexte invalide')
    D = Path('/root/mrjam-corrections/vision-mcp-configuration')/REV
    TIMER = 'vision-mcp-return-'+REV[:12]
    require(Path(__file__).resolve() == D/'payload/promote.py', 'Opérateur inattendu')
    try:
        if phase == 'launch':
            # Le timer peut interrompre ce groupe après disparition de la CI.
            subprocess.run(systemd_command('vision-mcp-deploy-'+REV[:12])+['--wait', '--pipe', '--collect',
                            sys.executable, '-B', __file__, 'deployer', REV], check=True)
        elif phase == 'witness':
            run(['nix-instantiate', '--version'])
            with urllib.request.urlopen('https://vision.mrj.am/.well-known/oauth-protected-resource/mcp', timeout=10) as response:
                require(response.status == 200, 'TLS du processus indépendant indisponible')
            run(['systemctl', 'stop', TIMER+'-worker.service'])
            (D/'return-witness').write_text('ok')
        elif phase == 'diagnostic':
            print(json.dumps({name: json.loads((D/(name+'.json')).read_text())
                              for name in ('deployed', 'returned') if (D/(name+'.json')).exists()}))
        else:
            if phase in ('automatic-return', 'retour'):
                stop_if_loaded('vision-mcp-deploy-'+REV[:12]+'.service')
            with open('/root/mrjam-vision-mcp.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if phase == 'automatic-return' and (D/'deployed.json').exists():
                    pass
                else:
                    {'preparer': prepare, 'deployer': deploy, 'retour': rollback,
                     'automatic-return': rollback}[phase]()
    except Exception as e:
        # Ne jamais publier le corps d'une réponse HTTP ou les erreurs SQL/Nix.
        reason = str(e) if isinstance(e, (ValueError, RuntimeError)) else type(e).__name__
        if isinstance(e, FileNotFoundError) and e.filename in ('nix-instantiate', 'systemctl', 'nix-env', 'nix-store', 'runuser'):
            reason += ': '+e.filename
        print(json.dumps(dict(phase=phase, stopped=True, reason=reason)))
        sys.exit(1)
