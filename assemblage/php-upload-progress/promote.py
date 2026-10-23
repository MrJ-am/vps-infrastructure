"""Avis du 23 octobre : configuration déclarative, sondes FPM et retour fermé.

Réutilise les primitives de sauvegarde/restauration, construction et sondes déjà
exploitées le 21 octobre. Aucun corps, compte, secret ou contenu privé publié.
"""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import socket
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('php_security_existing', ROOT/'assemblage/nextcloud-php-security/promote.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
legacy.PROTECTED = (*legacy.PROTECTED, 'nginx')
require, run, log = legacy.require, legacy.run, legacy.log
KEY = 'session.upload_progress.enabled'
ADMIN = 'php_admin_flag['+KEY+']'


def disabled(value):
    return value is False or str(value).lower() in ('', '0', 'off', 'false', 'no')


def validate(before, after):
    require(set(before['pools']) == set(after['pools']) == {'nextcloud'}, 'Unexpected PHP pool inventory')
    require(not before['apache'] and not after['apache'], 'Unexpected Apache runtime')
    require(after['phpOptions'].get(KEY) == 'Off', 'Nextcloud php.ini protection missing')
    old, new = copy.deepcopy(before), copy.deepcopy(after)
    for conf in (old, new):
        conf['phpOptions'].pop(KEY, None)
    require(old['phpOptions'] == new['phpOptions'], 'Other PHP options changed')
    require(after['fpmOptions'].strip() == (before['fpmOptions'].rstrip()+'\n'+KEY+' = Off').strip(),
            'Global FPM options differ beyond mitigation')
    for conf in (old, new):
        conf['nc']['pool'].pop(ADMIN, None)
        conf['pools']['nextcloud']['settings'].pop(ADMIN, None)
    require(after['pools']['nextcloud']['settings'].get(ADMIN) is False, 'FPM admin flag missing')
    old_pool, new_pool = old['pools']['nextcloud'], new['pools']['nextcloud']
    require(old_pool['phpOptions'] == new_pool['phpOptions'].replace(KEY+' = Off', '', 1).strip()
            or old_pool['phpOptions'].strip() == new_pool['phpOptions'].replace(KEY+' = Off', '', 1).strip(),
            'Other pool PHP options changed')
    old_pool.pop('phpOptions'); new_pool.pop('phpOptions')
    require(old_pool == new_pool, 'Other pool configuration changed')
    changes = legacy.validate(old, new)
    allowed = {'phpfpm-nextcloud.service', 'nextcloud-setup.service', 'nextcloud-cron.service',
               'nextcloud-backup.service', 'nextcloud-update-db.service',
               'systemd-tmpfiles-resetup.service', 'dbus-broker.service'}
    require(set(changes) <= allowed, 'Unexpected unit changes: '+','.join(sorted(set(changes)-allowed)))
    return changes


def evaluate(path):
    return json.loads(run(['nix-instantiate', '-I', 'nixpkgs='+legacy.TARGET['nixpkgs'],
                          '--eval', '--strict', '--json', HERE/'evaluation.nix',
                          '--arg', 'configuration', path], timeout=300))


def record(kind, data):
    return struct.pack('!BBHHBB', 1, kind, 1, len(data), 0, 0)+data


def receive(sock, length):
    data = b''
    while len(data) < length:
        part = sock.recv(length-len(data))
        require(bool(part), 'Truncated FastCGI response')
        data += part
    return data


def fastcgi(sock, filename):
    params = {'SCRIPT_FILENAME':str(filename), 'SCRIPT_NAME':'/php-security-probe.php',
              'REQUEST_METHOD':'GET', 'REQUEST_URI':'/php-security-probe.php',
              'SERVER_PROTOCOL':'HTTP/1.1', 'GATEWAY_INTERFACE':'CGI/1.1',
              'SERVER_NAME':'localhost', 'SERVER_PORT':'443', 'HTTPS':'on',
              'REMOTE_ADDR':'127.0.0.1', 'CONTENT_LENGTH':'0'}
    def length(n):
        return bytes([n]) if n < 128 else struct.pack('!I', n | 0x80000000)
    encoded = b''.join(length(len(k.encode()))+length(len(v.encode()))+k.encode()+v.encode()
                       for k, v in params.items())
    sock.sendall(record(1, struct.pack('!HB5x', 1, 0))+record(4, encoded)+record(4, b'')+record(5, b''))
    output = b''
    while True:
        version, kind, request, size, padding, _ = struct.unpack('!BBHHBB', receive(sock, 8))
        require(version == 1 and request == 1, 'Unexpected FastCGI record')
        data = receive(sock, size)
        receive(sock, padding)
        if kind == 6:
            output += data
            require(len(output) < 16384, 'Unexpected probe output')
        if kind == 3:
            require(len(data) == 8 and struct.unpack('!IB3x', data) == (0, 0), 'FastCGI request failed')
            break
    headers, separator, body = output.partition(b'\r\n\r\n')
    require(bool(separator), 'Missing FastCGI headers')
    return json.loads(body)


def runtime(conf, mitigation=False):
    require(set(conf['pools']) == {'nextcloud'} and not conf['apache'], 'Unexpected PHP handlers')
    owner = pwd.getpwnam('nextcloud')
    # Fichier temporaire hors racine Web, supprimé après la requête Unix privée.
    with tempfile.TemporaryDirectory(prefix='.php-security-', dir='/var/lib/nextcloud') as temp:
        folder = Path(temp)
        os.chown(folder, owner.pw_uid, owner.pw_gid)
        probe = folder/'probe.php'
        probe.write_text('<?php echo json_encode(["version"=>PHP_VERSION,"sapi"=>PHP_SAPI,'
                         '"uploadProgress"=>ini_get("session.upload_progress.enabled"),'
                         '"ini"=>php_ini_loaded_file()]);')
        probe.chmod(0o400)
        os.chown(probe, owner.pw_uid, owner.pw_gid)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(20)
            sock.connect(conf['pools']['nextcloud']['socket'])
            actual = fastcgi(sock, probe)
    require(actual['version'] == '8.4.27' and actual['sapi'] == 'fpm-fcgi', 'Unexpected serving PHP')
    require(re.fullmatch('/nix/store/[a-z0-9]{32}-php.ini', actual['ini']), 'Unexpected FPM ini path')
    pid = run(['systemctl', 'show', 'phpfpm-nextcloud', '-p', 'MainPID', '--value'])
    require(re.fullmatch('[1-9][0-9]*', pid), 'FPM not running')
    require(run(['/proc/'+pid+'/exe', '-v']).startswith('PHP 8.4.27 '), 'Unpatched running FPM binary')
    # Le wrapper CLI/cron est vérifié séparément, sans lire la configuration privée.
    cli = run([conf['php']+'/bin/php', '-r', 'echo json_encode(ini_get("session.upload_progress.enabled"));'])
    cli = json.loads(cli)
    if mitigation:
        require(disabled(actual['uploadProgress']) and disabled(cli), 'Mitigation not active in PHP')
    log('serving-php-observed', phpVersion=actual['version'], sapi=actual['sapi'],
        sessionUploadProgressEnabled=not disabled(actual['uploadProgress']),
        cliSessionUploadProgressEnabled=not disabled(cli), poolCount=len(conf['pools']))
    return actual


def owns_entry():
    return Path('/etc/nixos/configuration.nix').read_text() == '{ imports = [ '+str(ROOT/'candidate.nix')+' ]; }\n'


def disarm():
    run(['systemctl', 'stop', 'php-upload-return-'+legacy.REV[:12]+'.timer'])


def restore_closed(state):
    if not owns_entry():
        log('stale-return-skipped', foreignConfigurationPreserved=True)
        return
    (ROOT/'returned').touch()
    legacy.close_gate()
    legacy.entry(ROOT/'base.nix')
    legacy.switch(state['baseline'])
    legacy.persist(state['baseline'])
    legacy.assert_closed()
    log('returned-closed', oldDatabaseRestored=False)


def apply():
    source = Path('/etc/nixos/configuration.nix')
    target = legacy.TARGET
    require(legacy.current() == str(Path('/nix/var/nix/profiles/system').resolve()) == target['generation'],
            'Production generation changed')
    require(legacy.digest(source) == target['entrySha256'], 'Production entry changed')
    require(not legacy.BLOCK.exists(), 'Previous PHP operation is blocked')
    (ROOT/'base.nix').write_bytes(source.read_bytes())
    baseline = evaluate(ROOT/'base.nix')
    require(baseline['generation'] == target['generation'] and not baseline['errors'], 'Baseline does not reproduce production')
    runtime(baseline)
    (ROOT/'candidate.nix').write_text('{ imports = [ ./base.nix ./assemblage/php-upload-progress/module.nix ]; }\n')
    candidate = evaluate(ROOT/'candidate.nix')
    changes = validate(baseline, candidate)
    generation = legacy.build(ROOT/'candidate.nix', 'mitigated')
    require(generation == candidate['generation'], 'Candidate changed during build')
    legacy.php_check(candidate)
    require(disabled(json.loads(run([candidate['php']+'/bin/php', '-r', 'echo json_encode(ini_get("'+KEY+'"));']))),
            'Candidate CLI mitigation missing')
    legacy.code_integrity(candidate)
    state = {'revision':legacy.REV, 'baseline':baseline['generation'], 'protectedPids':legacy.pids(),
             'candidate':generation, 'complete':False}
    legacy.save_state(state)
    run(['nix-store', '--add-root', str(ROOT/'baseline-root'), '--indirect', '-r', baseline['generation']])
    run(['nix-store', '--add-root', str(ROOT/'python-root'), '--indirect', '-r', str(Path(sys.executable).resolve().parents[1])])
    run(['systemd-run', '--unit=php-upload-return-'+legacy.REV[:12], '--on-active=15m',
         '--timer-property=AccuracySec=1s', '--setenv=PATH='+os.environ['PATH'],
         sys.executable, str(HERE/'promote.py'), 'return', legacy.REV])
    try:
        require(legacy.current() == target['generation'] and legacy.digest(source) == target['entrySha256'],
                'Concurrent production change')
        # Armer le propriétaire du retour avant de bloquer PHP ; la configuration
        # n'est activée qu'après sauvegarde chiffrée et restauration isolée.
        legacy.entry(ROOT/'candidate.nix')
        legacy.close_gate()
        legacy.assert_closed()
        helper = legacy.backup(state, baseline)
        # Exercer le même exécutable indépendant que le minuteur, pendant que
        # PHP est déjà arrêté. Le retour ne restaure aucune donnée ancienne.
        run([sys.executable, HERE/'promote.py', 'return', legacy.REV], timeout=600)
        require((ROOT/'returned').is_file() and legacy.current() == baseline['generation']
                and str(Path('/nix/var/nix/profiles/system').resolve()) == baseline['generation'],
                'Independent return not verified')
        require(legacy.pids() == state['protectedPids'], 'Protected service restarted during return check')
        log('independent-return-verified', restoresOldDatabase=False, closedPhp=True)
        (ROOT/'returned').unlink()
        legacy.entry(ROOT/'candidate.nix')
        require(owns_entry() and not (ROOT/'returned').exists(), 'Independent return already executed')
        legacy.switch(generation)
        legacy.php_check(candidate)
        legacy.occ_status(generation)
        require(helper.schema(lambda q: helper.sql(Path(candidate['postgres'])/'bin', '/run/postgresql', 'nextcloud', q))
                == state['dbHashes'], 'Production data changed while closed')
        require(legacy.pids() == state['protectedPids'], 'Protected service restarted')
        legacy.persist(generation)
        require(owns_entry() and not (ROOT/'returned').exists(), 'Independent return already executed')
        legacy.BLOCK.unlink()
        run(['systemctl', 'start', 'phpfpm-nextcloud.service', 'nextcloud-cron.timer'])
        runtime(candidate, mitigation=True)
        legacy.probe()
        require(not legacy.BLOCK.exists() and not (ROOT/'returned').exists(), 'Independent return executed')
        require(legacy.pids() == state['protectedPids'], 'Protected service restarted after reopening')
        state['complete'] = True
        legacy.save_state(state)
        disarm()
        log('mitigated-and-reopened', generation=generation, phpVersion='8.4.27', nextcloudVersion='34.0.4',
            sessionUploadProgressEnabled=False, cliSessionUploadProgressEnabled=False,
            changedUnits=changes, backupRestoredInIsolation=True, protectedPidsUnchanged=True,
            independentReturnVerified=True, bootGenerationCommitted=True, restoredOldDatabase=False,
            oidcPkce=True, anonymousDavDenied=True)
    except BaseException:
        restore_closed(state)
        disarm()
        raise


def main():
    operation, revision = sys.argv[1:]
    require(operation in ('audit', 'apply', 'return') and re.fullmatch('[a-f0-9]{40}', revision), 'Invalid closed operation')
    require(os.geteuid() == 0, 'Root required')
    os.umask(0o077)
    legacy.D, legacy.REV = ROOT, revision
    legacy.TARGET = json.loads((HERE/'target.json').read_text())
    (ROOT/'payload').mkdir(exist_ok=True)
    helper = ROOT/'payload/monolithe-sauvegarde.py'
    if not helper.exists():
        helper.symlink_to(ROOT/'scripts/monolithe-sauvegarde.py')
    # Le retour indépendant doit pouvoir interrompre une opération bloquée qui
    # détient encore le verrou. Aucun nouveau travail administratif n'est lancé.
    if operation == 'return':
        state = json.loads((ROOT/'state.json').read_text())
        if not state.get('complete'):
            restore_closed(state)
        return
    with (legacy.BLOCK.parent/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if operation == 'apply':
            apply()
        else:
            conf = evaluate(Path('/etc/nixos/configuration.nix'))
            actual = runtime(conf)
            legacy.probe()
            log('audit-complete', generation=legacy.current(), bootGeneration=str(Path('/nix/var/nix/profiles/system').resolve()),
                phpVersion=conf['phpVersion'], sessionUploadProgressEnabled=not disabled(actual['uploadProgress']),
                declarationProtected=conf['phpOptions'].get(KEY) == 'Off',
                fpmAdminProtected=conf['pools']['nextcloud']['settings'].get(ADMIN) is False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        log('stopped', error=str(error), privateDataPrinted=False)
        sys.exit(1)
