"""Qualification locale réelle du module Nix et de ses gardes de promotion."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'assemblage/php-upload-progress/'
spec = importlib.util.spec_from_file_location('upload_progress', ROOT/PREFIX/'promote.py')
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def main():
    nix, nixpkgs = os.environ['SECURITY_NIX_INSTANTIATE'], os.environ['SECURITY_NIXPKGS']
    with tempfile.TemporaryDirectory(prefix='upload-progress-') as tmp:
        configs = {}
        for name, mitigation in (('before', False), ('after', True)):
            modules = [ROOT/'assemblage/nextcloud-php-security'/n for n in ('fixture.nix', 'guard.nix', 'module.nix')]
            if mitigation:
                modules.append(ROOT/PREFIX/'module.nix')
            config = Path(tmp)/(name+'.nix')
            config.write_text('{ imports = [ '+' '.join(map(str, modules))+' ]; }\n')
            configs[name] = json.loads(subprocess.check_output([nix, '-I', 'nixpkgs='+nixpkgs,
                '--eval', '--strict', '--json', str(ROOT/PREFIX/'evaluation.nix'),
                '--arg', 'configuration', str(config)], text=True))
        changes = operator.validate(configs['before'], configs['after'])
        cases = []
        for section, key, value in [('phpOptions', 'memory_limit', '999G'),
                                    ('phpOptions', operator.KEY, 'On')]:
            changed = copy.deepcopy(configs['after']); changed[section][key] = value; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['pools']['nextcloud']['settings'][operator.ADMIN] = True; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['nc']['settings']['user_oidc']['auto_provision'] = True; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['units']['postgresql.service'] += '\nExecStart=/unsafe'; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['hosts']['cloud.mrj.am']['extra'] = ''; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['pools']['other'] = changed['pools']['nextcloud']; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['apache'] = True; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['phpVersion'] = '8.4.24'; cases.append(changed)
        changed = copy.deepcopy(configs['after']); changed['pools']['nextcloud']['phpOptions'] += '\nmemory_limit=999G'; cases.append(changed)
        for changed in cases:
            try:
                operator.validate(configs['before'], changed)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Unsafe candidate accepted')
        # Transport FastCGI : fragments réseau, corps JSON et fin de requête.
        client, server = socket.socketpair()
        expected = {'version':'8.4.27','sapi':'fpm-fcgi','uploadProgress':''}
        def respond():
            with server:
                server.recv(8192)
                reply = operator.record(6, b'Content-type: application/json\r\n\r\n'+json.dumps(expected).encode())
                reply += operator.record(3, struct.pack('!IB3x', 0, 0))
                for i in range(0, len(reply), 3):
                    server.sendall(reply[i:i+3])
        thread = threading.Thread(target=respond)
        thread.start()
        with client:
            client.settimeout(5)
            assert operator.fastcgi(client, '/private/probe.php') == expected
        thread.join()
        for value in ['', '0', 'Off', False]: assert operator.disabled(value)
        for value in ['1', 'On', True]: assert not operator.disabled(value)
        with mock.patch.object(operator, 'owns_entry', return_value=False), \
             mock.patch.object(operator, 'log'), mock.patch.object(operator.legacy, 'close_gate') as close:
            operator.restore_closed({})
            close.assert_not_called()
        files = [PREFIX+n for n in ('module.nix', 'evaluation.nix', 'promote.py', 'target.json')]
        files += ['assemblage/nextcloud-php-security/evaluation.nix', 'assemblage/nextcloud-php-security/promote.py',
                  'assemblage/nextcloud-php-security/fixture.nix', 'assemblage/nextcloud-php-security/guard.nix',
                  'assemblage/nextcloud-php-security/module.nix', 'assemblage/nextcloud-php-security/filter-test-cgi.sh',
                  'scripts/monolithe-sauvegarde.py', 'scripts/php-upload-progress-operation.py',
                  'scripts/php-upload-progress-qualify.py', '.github/workflows/php-upload-progress.yml',
                  'apps/nextcloud.nix']
        proof = {'passed':True, 'realNixEvaluation':True, 'unsafeChangesRejected':True,
                 'unsafeCandidateCases':len(cases), 'fastcgiFragmentedResponse':True,
                 'staleReturnPreservesNewDeployment':True, 'changedUnits':changes,
                 'nixpkgsRevision':'c5c4a43b0e8056328ec4529f735cabdb8f1942bb',
                 'confiance':'locale-non-attestee',
                 'sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
        (ROOT/PREFIX/'qualification-locale.json').write_text(json.dumps(proof, indent=2)+'\n')
        print(json.dumps({k:v for k,v in proof.items() if k != 'sha256'}))


if __name__ == '__main__':
    main()
