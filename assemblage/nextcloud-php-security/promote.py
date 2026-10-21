"""Correctif PHP borné : confinement persistant, sauvegarde et retour fermé.

Le retour remet uniquement le code confiné, jamais une ancienne base. Ni secret,
ni contenu métier, ni journaux HTTP ne sont imprimés. Aucun shell libre en entrée.
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
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# Nginx charge la réponse de confinement par son mécanisme NixOS de redémarrage.
# Les autres processus, dont les applications et PostgreSQL, restent identiques.
PROTECTED = ('postgresql', 'kanidm', 'mrjam-metier', 'forgejo', 'sshd', 'vision-embeddings', 'dbus-broker')
BLOCK = Path('/var/lib/nextcloud-php-security/blocked')
MINIMUM = {(8, 2): 35, (8, 3): 36, (8, 4): 27, (8, 5): 12}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def patched(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    if not match:
        return False
    major, minor, patch = map(int, match.groups())
    return (major, minor) in MINIMUM and patch >= MINIMUM[major, minor]


def validate(before, after, containment=False):
    require(not after['errors'], 'Nix assertions refused')
    for key in ('nc', 'kanidm', 'postgres', 'age', 'recipient'):
        require(before[key] == after[key], 'Protected configuration differs: '+key)
    require(set(before['hosts']) == set(after['hosts']), 'Host inventory differs')
    for name in before['hosts']:
        if containment and name == 'cloud.mrj.am':
            a, b = dict(before['hosts'][name]), dict(after['hosts'][name])
            require(b.pop('extra') == 'return 503;\n\n'+a.pop('extra') or
                    after['hosts'][name]['extra'].replace('return 503;', '', 1).strip() == before['hosts'][name]['extra'].strip(),
                    'Containment changed existing Nginx filters')
            require(a == b, 'Containment changed Nextcloud routes')
        else:
            require(before['hosts'][name] == after['hosts'][name], 'Virtual host differs: '+name)
    changes = sorted(n for n in set(before['units']) | set(after['units'])
                     if before['units'].get(n) != after['units'].get(n))
    allowed = lambda n: n.startswith('nextcloud-') or n in (
        'nginx.service', 'phpfpm-nextcloud.service', 'systemd-tmpfiles-resetup.service', 'dbus-broker.service')
    require(all(allowed(n) for n in changes), 'Unexpected service changes: '+','.join(n for n in changes if not allowed(n)))
    if 'systemd-tmpfiles-resetup.service' in changes:
        stable = lambda s: '\n'.join(x for x in s.splitlines() if not x.startswith('X-Restart-Triggers='))
        require(stable(before['units']['systemd-tmpfiles-resetup.service']) ==
                stable(after['units']['systemd-tmpfiles-resetup.service']), 'Tmpfiles command differs')
    if 'dbus-broker.service' in changes:
        # Le profil global contient le nouveau wrapper occ ; NixOS recharge D-Bus.
        stable = lambda s: '\n'.join(x for x in s.splitlines() if not x.startswith('X-Restart-Triggers='))
        require('X-ReloadIfChanged=true' in after['units']['dbus-broker.service'] and
                stable(before['units']['dbus-broker.service']) == stable(after['units']['dbus-broker.service']),
                'D-Bus changed beyond its profile reload trigger')
    require('ConditionPathExists=!'+str(BLOCK) in after['units']['phpfpm-nextcloud.service'], 'Missing persistent gate')
    require('ConditionPathExists=!'+str(BLOCK) in after['units']['nextcloud-cron.service'], 'Missing cron gate')
    require(after['phpVersion'] == ('8.4.24' if containment else '8.4.27'), 'Wrong PHP version')
    return changes


def run(args, *, input=None, timeout=180):
    p = subprocess.run(list(map(str, args)), input=input, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        with (D/'command-private.log').open('a') as f:
            f.write('\n'+p.stdout+'\n'+p.stderr)
        raise RuntimeError('Command failed: '+Path(str(args[0])).name+'; private diagnostic retained')
    return p.stdout.strip()


def log(phase, **data):
    print(json.dumps({'phase': phase, **data}), flush=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def current():
    return str(Path('/run/current-system').resolve())


def pids():
    return {n: run(['systemctl', 'show', n, '-p', 'MainPID', '--value']) for n in PROTECTED}


def retained_pids(before, after):
    return all(before.get(name) == after.get(name) for name in PROTECTED)


def evaluate(path):
    return json.loads(run(['nix-instantiate', '-I', 'nixpkgs='+TARGET['nixpkgs'], '--eval', '--strict', '--json',
                          str(D/'payload/evaluation.nix'), '--arg', 'configuration', str(path)], timeout=300))


def build(config, name):
    log('build-started', artifact=name)
    expression = '(import <nixpkgs/nixos/lib/eval-config.nix> {system="x86_64-linux";modules=['+str(config)+'];}).config.system.build.toplevel'
    with (D/(name+'-build-private.log')).open('a') as diagnostic:
        p = subprocess.run(['nix-build', '-I', 'nixpkgs='+TARGET['nixpkgs'], '--no-out-link', '--max-jobs', '1', '--cores', '2',
                            '--expr', expression], stdout=subprocess.PIPE, stderr=diagnostic, text=True, timeout=4200)
    require(p.returncode == 0, 'Build failed; diagnostic retained privately')
    generation = p.stdout.strip()
    require(re.fullmatch('/nix/store/[a-z0-9]{32}-nixos-system-[^/\n]+', generation), 'Unexpected build output')
    run(['nix-store', '--add-root', str(D/(name+'-root')), '--indirect', '-r', generation])
    log('build-complete', artifact=name, generation=generation)
    return generation


def close_gate():
    BLOCK.parent.mkdir(mode=0o700, exist_ok=True)
    BLOCK.write_text(REV+'\n')
    BLOCK.chmod(0o600)
    for unit in ('phpfpm-nextcloud', 'nextcloud-cron'):
        dropin = Path('/run/systemd/system')/(unit+'.service.d')
        dropin.mkdir(mode=0o755, exist_ok=True)
        (dropin/'99-php-security.conf').write_text('[Unit]\nConditionPathExists=!'+str(BLOCK)+'\n')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'stop', 'nextcloud-cron.timer', 'nextcloud-cron.service', 'phpfpm-nextcloud.service'])
    require(run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'MainPID', '--value']) == '0', 'PHP still running')


def entry(path):
    temp = Path('/etc/nixos/.nextcloud-php-security.nix')
    temp.write_text('{ imports = [ '+str(path)+' ]; }\n')
    temp.chmod(0o644)
    temp.replace('/etc/nixos/configuration.nix')


def http(path, method='GET'):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    request = urllib.request.Request('https://cloud.mrj.am'+path, data=b'user=&password=' if method == 'POST' else None)
    try:
        return urllib.request.build_opener(NoRedirect).open(request, timeout=20)
    except urllib.error.HTTPError as error:
        return error


def assert_closed(code=None):
    require(BLOCK.is_file(), 'Gate marker missing')
    run(['systemctl', 'start', 'phpfpm-nextcloud.service'])
    require(run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'MainPID', '--value']) == '0', 'Gate did not block PHP')
    require(run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'ConditionResult', '--value']) == 'no', 'Condition not enforced')
    for path in ('/status.php', '/login', '/remote.php/dav/'):
        with http(path) as response:
            require(response.code in ([code] if code else [502, 503]), 'PHP endpoint not closed')


def switch(generation):
    run([generation+'/bin/switch-to-configuration', 'test'], timeout=360)
    require(current() == generation, 'Wrong active generation')


def persist(generation):
    run(['nix-env', '--profile', '/nix/var/nix/profiles/system', '--set', generation])
    run([generation+'/bin/switch-to-configuration', 'switch'], timeout=360)
    require(current() == generation == str(Path('/nix/var/nix/profiles/system').resolve()), 'Boot generation not committed')


def save_state(state):
    (D/'state.json').write_text(json.dumps(state))


def return_closed(state):
    close_gate()
    require(Path('/etc/nixos/configuration.nix').read_text() in
            ['{ imports = [ '+str(D/name)+' ]; }\n' for name in ('contained.nix', 'patched.nix')],
            'Concurrent configuration prevents automatic code return; PHP kept closed')
    entry(D/'contained.nix')
    switch(state['contained'])
    persist(state['contained'])
    assert_closed(503)
    log('returned-to-persistent-containment', restoredOldDatabase=False)


def backup(state, conf):
    # Réutilisation des primitives de snapshot/hachage déjà exploitées et qualifiées.
    spec = importlib.util.spec_from_file_location('backup_helpers', D/'payload/monolithe-sauvegarde.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    pg = Path(conf['postgres'])/'bin'
    age = Path(conf['age'])/'bin/age'
    keygen = Path(conf['age'])/'bin/age-keygen'
    run(['nix-store', '-r', conf['age']])
    destination = Path('/var/backup/nextcloud-php-security')
    destination.mkdir(mode=0o700, exist_ok=True)
    destination = destination/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+REV[:12])
    destination.mkdir(mode=0o700)
    isolated = Path('/var/lib')/('nextcloud-php-restore-'+REV[:12])
    isolated.mkdir(mode=0o700)
    owner = pwd.getpwnam('postgres')
    os.chown(isolated, owner.pw_uid, owner.pw_gid)
    started = False
    try:
        with tempfile.TemporaryDirectory(prefix='backup-', dir=D) as temp:
            temp = Path(temp)
            key = temp/'key'
            run([keygen, '-o', key])
            public = run([keygen, '-y', key])
            host = Path('/etc/ssh/ssh_host_ed25519_key')
            host_public = host.with_suffix('.pub').read_text().strip()
            run([age, '-r', conf['recipient'], '-r', host_public, '-o', destination/'key.age', key])
            run([age, '-d', '-i', host, '-o', temp/'host-recovered-key', destination/'key.age'])
            require(digest(key) == digest(temp/'host-recovered-key'), 'Host recovery key round trip failed')
            hashes = helper.dump_snapshot(pg, 'nextcloud', temp/'db.dump')
            run(['tar', '--numeric-owner', '-C', '/var/lib/nextcloud', '-cpf', temp/'files.tar', 'config', 'data'], timeout=300)
            run(['tar', '-C', temp, '-cf', temp/'snapshot.tar', 'db.dump', 'files.tar'])
            run([age, '-r', public, '-o', destination/'snapshot.tar.age', temp/'snapshot.tar'], timeout=300)
            run([age, '-d', '-i', temp/'host-recovered-key', '-o', temp/'recovered.tar', destination/'snapshot.tar.age'], timeout=300)
            require(digest(temp/'snapshot.tar') == digest(temp/'recovered.tar'), 'Encrypted backup differs')
            restored = temp/'restored'
            restored.mkdir()
            run(['tar', '-xf', temp/'recovered.tar', '-C', restored])
            files = restored/'files'
            files.mkdir()
            run(['tar', '-xf', restored/'files.tar', '-C', files], timeout=300)
            require((files/'config/config.php').is_file() and (files/'data').is_dir(), 'File restore failed')
            # Nouveau cluster sans écoute TCP ; aucun objet de la production n'est restauré.
            run(['runuser', '-u', 'postgres', '--', pg/'initdb', '-D', isolated/'data', '--auth-local=trust',
                 '--auth-host=reject', '--no-locale', '--encoding=UTF8'])
            run(['runuser', '-u', 'postgres', '--', pg/'pg_ctl', '-D', isolated/'data', '-l', isolated/'server.log',
                 '-w', '-t', '20', '-o', "-c listen_addresses='' -c unix_socket_directories="+str(isolated)+
                 ' -c log_min_error_statement=panic -c log_min_messages=fatal', 'start'])
            started = True
            helper.sql(pg, isolated, 'postgres', 'CREATE DATABASE nextcloud_restore')
            with (restored/'db.dump').open('rb') as source:
                p = subprocess.run(['runuser', '-u', 'postgres', '--', str(pg/'pg_restore'), '--exit-on-error',
                                    '--no-owner', '--no-acl', '--host='+str(isolated), '--dbname=nextcloud_restore'],
                                   stdin=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
            require(p.returncode == 0, 'Isolated restore failed')
            require(helper.schema(lambda q: helper.sql(pg, isolated, 'nextcloud_restore', q)) == hashes, 'Restored database differs')
            state['dbHashes'] = hashes
            state['backup'] = str(destination)
            state['filesHash'] = digest(temp/'files.tar')
            save_state(state)
    finally:
        if started:
            run(['runuser', '-u', 'postgres', '--', pg/'pg_ctl', '-D', isolated/'data', '-m', 'fast', '-w', '-t', '20', 'stop'])
        require(not (isolated/'data/postmaster.pid').exists(), 'Restore cluster still running')
        shutil.rmtree(isolated)
    log('backup-restored-in-isolation', encrypted=True, ownerAndHostRecoveryVerified=True, productionDatabaseRestored=False)
    return helper


def php_check(conf):
    require(patched(conf['phpVersion']) and conf['phpVersion'] == TARGET['patchedPhp'], 'Unpatched PHP candidate')
    code = 'if(PHP_VERSION_ID!==80427){exit(1);}foreach(["pdo_pgsql","redis","apcu","intl","mbstring","sodium","curl","dom","zip","gd","systemd"] as $e){if(!extension_loaded($e)){exit(2);}}echo PHP_VERSION;'
    require(run([conf['php']+'/bin/php', '-r', code]) == TARGET['patchedPhp'], 'PHP or required extensions invalid')
    run(shlex.split(conf['fpm'])+['-tt'])
    run(shlex.split(conf['nginx'])+['-t'])


def occ_status(generation):
    result = json.loads(run(['runuser', '-u', 'nextcloud', '--', 'env', '-i', 'PATH=/run/current-system/sw/bin',
                             'USER=nextcloud', 'HOME=/var/lib/nextcloud', generation+'/sw/bin/nextcloud-occ', 'status', '--output=json']))
    require(result['installed'] and result['versionstring'] == '34.0.4' and
            not result['maintenance'] and not result['needsDbUpgrade'], 'Nextcloud status invalid')


def probe():
    with http('/status.php') as response:
        result = json.load(response)
    require(result['installed'] and result['versionstring'] == '34.0.4' and not result['maintenance'] and
            not result['needsDbUpgrade'], 'Nextcloud HTTP status invalid')
    url = 'https://cloud.mrj.am/login'
    for _ in range(6):
        with http(url.removeprefix('https://cloud.mrj.am')) as response:
            require(response.code in (301, 302, 303, 307), 'OIDC redirect missing')
            url = urllib.parse.urljoin(url, response.headers['Location'])
        if urllib.parse.urlsplit(url).hostname == 'log.mrj.am':
            break
        require(urllib.parse.urlsplit(url).hostname == 'cloud.mrj.am', 'Unexpected redirect host')
    parsed = urllib.parse.urlsplit(url)
    params = urllib.parse.parse_qs(parsed.query)
    require(parsed.hostname == 'log.mrj.am' and params.get('client_id') == ['mrjam-nextcloud'] and
            params.get('code_challenge_method') == ['S256'], 'OIDC or PKCE changed')
    for path in ('/login', '/index.php/login?direct=1'):
        with http(path, 'POST') as response:
            require(response.code == 403, 'Local password filter changed')
    with http('/remote.php/dav/') as response:
        require(response.code == 401, 'Anonymous DAV access not denied')


def correct():
    require(not (D/'state.json').exists(), 'Inspect existing operation before repeating')
    expected_generation = TARGET['generation']
    expected_entry = TARGET['entrySha256']
    source = Path('/etc/nixos/configuration.nix')
    previous = None
    if TARGET.get('resumeFrom'):
        resume = TARGET['resumeFrom']
        require(re.fullmatch('[a-f0-9]{40}', resume), 'Invalid resume revision')
        previous_dir = D.parent/resume
        previous = json.loads((previous_dir/'state.json').read_text())
        require(not previous.get('complete') and previous['baseline'] == TARGET['generation'], 'Wrong previous operation')
        require(retained_pids(previous['protectedPids'], pids()), 'An application process changed since containment')
        expected_generation = previous['contained']
        expected_entry = hashlib.sha256(('{ imports = [ '+str(previous_dir/'contained.nix')+' ]; }\n').encode()).hexdigest()
        source = previous_dir/'base.nix'
        require(digest(source) == TARGET['entrySha256'], 'Original production source differs')
    require(current() == expected_generation == str(Path('/nix/var/nix/profiles/system').resolve()), 'Production generation changed')
    require(digest('/etc/nixos/configuration.nix') == expected_entry, 'Production source changed')
    close_gate()
    assert_closed()
    (D/'base.nix').write_bytes(source.read_bytes())
    baseline = evaluate(D/'base.nix')
    require(not baseline['errors'] and baseline['generation'] == TARGET['generation'], 'Source does not reproduce original installed generation')
    require(baseline['phpVersion'] == TARGET['previousPhp'], 'Different PHP installation')
    (D/'contained.nix').write_text('{ imports = [ ./base.nix ./payload/guard.nix ./payload/containment.nix ]; }\n')
    (D/'patched.nix').write_text('{ imports = [ ./base.nix ./payload/guard.nix ./payload/module.nix ]; }\n')
    contained = evaluate(D/'contained.nix')
    changed = validate(baseline, contained, containment=True)
    generation = build(D/'contained.nix', 'contained')
    require(generation == contained['generation'], 'Containment derivation changed')
    state = {'revision': REV, 'baseline': baseline['generation'], 'protectedPids': pids(), 'contained': generation}
    save_state(state)
    run(['nix-store', '--add-root', str(D/'baseline-root'), '--indirect', '-r', baseline['generation']])
    run(['nix-store', '--add-root', str(D/'python-root'), '--indirect', '-r', str(Path(sys.executable).resolve().parents[1])])
    helper = backup(state, baseline)
    run(shlex.split(contained['nginx'])+['-t'])
    require(current() == expected_generation and digest('/etc/nixos/configuration.nix') == expected_entry,
            'Production changed before containment')
    entry(D/'contained.nix')
    switch(generation)
    persist(generation)
    assert_closed(503)
    require(pids() == state['protectedPids'], 'Protected services restarted during containment')
    log('persistent-containment-active', generation=generation, changedUnits=changed, rebootProtected=True)
    try:
        candidate = evaluate(D/'patched.nix')
        changed = validate(baseline, candidate)
        generation = build(D/'patched.nix', 'patched')
        require(generation == candidate['generation'], 'Patched derivation changed')
        php_check(candidate)
        log('patched-runtime-checked', phpVersion=candidate['phpVersion'], requiredExtensions=True, fpmConfiguration=True)
        require(current() == state['contained'] and pids() == state['protectedPids'], 'Production changed during preparation')
        require(Path('/etc/nixos/configuration.nix').read_text() == '{ imports = [ '+str(D/'contained.nix')+' ]; }\n', 'Concurrent source edit')
        timer = 'nextcloud-php-return-'+REV[:12]
        run(['systemd-run', '--unit='+timer, '--on-active=15m', '--timer-property=AccuracySec=1s',
             '--setenv=PATH='+os.environ['PATH'], sys.executable, str(D/'payload/promote.py'), 'return', REV])
        state['patched'] = generation
        save_state(state)
        entry(D/'patched.nix')
        switch(generation)
        assert_closed()
        php_check(candidate)
        occ_status(generation)
        run(['runuser', '-u', 'nextcloud', '--', 'env', '-i', 'PATH=/run/current-system/sw/bin', 'USER=nextcloud',
             'HOME=/var/lib/nextcloud', generation+'/sw/bin/nextcloud-occ', 'integrity:check-core'], timeout=300)
        require(helper.schema(lambda q: helper.sql(Path(candidate['postgres'])/'bin', '/run/postgresql', 'nextcloud', q)) == state['dbHashes'], 'Production data changed before reopening')
        require(pids() == state['protectedPids'], 'Protected services restarted')
        persist(generation)
        # Vérification du binaire réellement sélectionné AVANT ouverture Web.
        require(candidate['php']+'/bin/php-fpm' in run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'ExecStart', '--value']), 'FPM unit does not use patched runtime')
        BLOCK.unlink()
        run(['systemctl', 'start', 'phpfpm-nextcloud.service', 'nextcloud-cron.timer'])
        pid = run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'MainPID', '--value'])
        require(re.fullmatch('[1-9][0-9]*', pid), 'FPM did not start')
        actual = run([str(Path('/proc')/pid/'exe'), '-v'])
        require(actual.startswith('PHP 8.4.27 '), 'Running FPM version differs')
        probe()
        require(pids() == state['protectedPids'], 'Protected services changed after reopening')
        run(['systemctl', 'stop', timer+'.timer'])
        state['complete'] = True
        save_state(state)
        log('corrected-and-reopened', generation=generation, phpVersion='8.4.27', nextcloudVersion='34.0.4',
            changedUnits=changed, protectedPidsUnchanged=True, backupRestoredInIsolation=True,
            oidcPkce=True, anonymousDavDenied=True, localPasswordDenied=True, coreIntegrity=True,
            bootGenerationCommitted=True, restoredOldDatabase=False)
    except BaseException:
        return_closed(state)
        raise


def main():
    global D, REV, TARGET
    operation, REV = sys.argv[1:]
    require(operation in ('correct', 'return') and re.fullmatch('[a-f0-9]{40}', REV), 'Invalid closed operation')
    require(os.geteuid() == 0, 'Root required')
    os.umask(0o077)
    D = Path('/root/mrjam-corrections/nextcloud-php-security')/REV
    TARGET = json.loads((D/'payload/target.json').read_text())
    with (BLOCK.parent/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if operation == 'return':
            return_closed(json.loads((D/'state.json').read_text()))
        else:
            correct()


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        log('stopped', error=str(error), privateDataPrinted=False)
        sys.exit(1)
