"""Qualification Nix réelle et refus des changements hors périmètre, en local."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shlex

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'assemblage/nextcloud-php-security/'


def main():
    nix = os.environ['SECURITY_NIX_INSTANTIATE']
    nixpkgs = os.environ['SECURITY_NIXPKGS']
    spec = importlib.util.spec_from_file_location('operator_php', ROOT/PREFIX/'promote.py')
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    versions = {
        '8.2.34': False, '8.2.35': True, '8.3.35': False, '8.3.36': True,
        '8.4.24': False, '8.4.26': False, '8.4.27': True, '8.4.28': True,
        '8.5.11': False, '8.5.12': True, '8.1.99': False, 'unknown': False,
        '8.4.27-dev': False,
    }
    assert all(operator.patched(v) is expected for v, expected in versions.items())
    pids = {name:'100' for name in operator.PROTECTED}
    assert operator.retained_pids(dict(pids, nginx='1'), dict(pids, nginx='2'))
    assert not operator.retained_pids(pids, dict(pids, postgresql='200'))
    expression = '''let pkgs=import NIXPKGS {system="x86_64-linux";};
      m=import MODULE {inherit pkgs;lib=pkgs.lib;}; p=m.services.nextcloud.phpPackage.content;
      checked=p.withExtensions ({enabled,...}:
        let filters=builtins.filter (x: x.extensionName=="filter") enabled; in
        assert builtins.length filters==1;
        assert builtins.all (x: x.doCheck && (x ? preCheck) && pkgs.lib.hasInfix "TEST_PHP_CGI_EXECUTABLE" x.preCheck) filters;
        enabled);
      in {package=toString checked;version=checked.version;}'''
    expression = expression.replace('NIXPKGS',nixpkgs).replace('MODULE',str(ROOT/PREFIX/'module.nix'))
    checked = json.loads(subprocess.check_output([nix,'--eval','--strict','--json','--expr',expression],text=True))
    assert checked['version']=='8.4.27'
    with tempfile.TemporaryDirectory(prefix='php-security-', dir=ROOT/'.cache') as tmp:
        tmp = Path(tmp)
        fake = tmp/'php-cgi-fake'
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        fake.chmod(0o700)
        wrapper = tmp/'php-cgi-with-filter'
        wrapper.write_text('#!/bin/sh\nphp_filter_test_cgi='+shlex.quote(str(fake))+'\nphp_filter_test_module=/build/filter/modules/filter.so\n'+
                           (ROOT/PREFIX/'filter-test-cgi.sh').read_text())
        wrapper.chmod(0o700)
        args = ['-n','-d','memory_limit=12M']
        assert subprocess.check_output([str(wrapper),*args],env={},text=True).splitlines() == ['-d','extension=/build/filter/modules/filter.so',*args]
        args = ['-n','-d','extension=/build/filter/modules/filter.so','-d','memory_limit=12M']
        assert subprocess.check_output([str(wrapper),*args],env={},text=True).splitlines() == args
        fixture = ROOT/PREFIX/'fixture.nix'
        data = {}
        for name, modules in {
            'base': [fixture],
            'contained': [fixture, ROOT/PREFIX/'guard.nix', ROOT/PREFIX/'containment.nix'],
            'patched': [fixture, ROOT/PREFIX/'guard.nix', ROOT/PREFIX/'module.nix'],
        }.items():
            config = tmp/(name+'.nix')
            config.write_text('{ imports = [ '+' '.join(map(str, modules))+' ]; }\n')
            output = subprocess.check_output([nix, '-I', 'nixpkgs='+nixpkgs, '--eval', '--strict', '--json',
                                              str(ROOT/PREFIX/'evaluation.nix'), '--arg', 'configuration', str(config)], text=True)
            data[name] = json.loads(output)
        assert not data['base']['errors'], data['base']['errors']
        (ROOT/'.cache/nextcloud-php-evaluation.json').write_text(json.dumps(data))
        contained_changes = operator.validate(data['base'], data['contained'], containment=True)
        patched_changes = operator.validate(data['base'], data['patched'])
        assert data['patched']['phpVersion'] == '8.4.27' and '8.4.27' in data['patched']['php']
        assert '8.4.27' in data['patched']['fpm']
        cases = []
        changed = copy.deepcopy(data['patched']); changed['units']['postgresql.service'] += '\nExecStart=/unsafe'
        cases.append(changed)
        changed = copy.deepcopy(data['patched']); changed['hosts']['vision.mrj.am']['extra'] += 'return 200;'
        cases.append(changed)
        changed = copy.deepcopy(data['patched']); changed['nc']['settings']['user_oidc']['auto_provision'] = True
        cases.append(changed)
        changed = copy.deepcopy(data['patched']); changed['phpVersion'] = '8.4.26'
        cases.append(changed)
        changed = copy.deepcopy(data['patched']); changed['units']['phpfpm-nextcloud.service'] = 'No guard'
        cases.append(changed)
        changed = copy.deepcopy(data['patched']); changed['units']['dbus-broker.service'] += '\nExecStart=/unsafe'
        cases.append(changed)
        for changed in cases:
            try:
                operator.validate(data['base'], changed)
            except RuntimeError:
                pass
            else:
                raise AssertionError('An unsafe candidate was accepted')
        files = [PREFIX+n for n in ('guard.nix','containment.nix','module.nix','filter-test-cgi.sh','evaluation.nix','target.json','promote.py','fixture.nix')]
        files += ['scripts/monolithe-sauvegarde.py','scripts/nextcloud-php-security-operation.py',
                  'scripts/nextcloud-php-security-qualify.py','.github/workflows/nextcloud-php-security.yml',
                  'scripts/nextcloud-php-security.sh']
        proof = {'passed':True,'realNixEvaluation':True,'unsafeChangesRejected':True,
                 'versionBoundaryCases':len(versions),'unsafeCandidateCases':len(cases),
                 'filterCgiEmptyEnvironment':True,'filterCgiDuplicateAvoided':True,
                 'filterCgiTestAdaptationEffective':True,
                 'containedChangedUnits':contained_changes,'patchedChangedUnits':patched_changes,
                 'phpVersion':data['patched']['phpVersion'],'nixpkgsRevision':'c5c4a43b0e8056328ec4529f735cabdb8f1942bb',
                 'confiance':'locale-non-attestee','sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
        (ROOT/PREFIX/'qualification-locale.json').write_text(json.dumps(proof,indent=2)+'\n')
        print(json.dumps({k:v for k,v in proof.items() if k != 'sha256'}))


if __name__ == '__main__':
    (ROOT/'.cache').mkdir(exist_ok=True)
    main()
