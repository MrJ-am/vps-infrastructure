"""Read-only check of the exact production wrapper and transitive store closure."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PROPOSAL=Path('/nix/store/1j61zvqin8df0vdazsdxlfssf5rdc54z-mrjam-rules-bootstrap-proposal-1')


def check(package):
    checks=[]
    def require(value,name):
        if not value:raise RuntimeError(name)
        checks.append(name)
    package=Path(package)
    require(package.parent==Path('/nix/store') and package.is_dir(),'immutable-package-root')
    files={'adoption.py':HERE/'adoption.py','identity.py':HERE/'identity.py',
        'merge_transport.py':HERE/'merge_transport.py','sso.py':HERE.parents[1]/'deployment/forgejo_sso_probe.py'}
    for name in ('contract.py','signer.py','collector.py'):files[name]=HERE.parent/'authority-v1'/name
    for name in ('review_contract.py','api_projection.py','read_transport_v2.py'):files[name]=HERE.parent/'review-v1'/name
    require(all((package/'libexec'/name).read_bytes()==path.read_bytes() for name,path in files.items()),'ten-modules-byte-exact')
    require((package/'libexec/bootstrap-entry.py').read_text()==(HERE/'entry.py').read_text().replace('@PROPOSAL@',str(PROPOSAL)),
        'entry-exact-proposal-substitution')
    require('proposalPackage ? builtins.storePath '+str(PROPOSAL) in (HERE/'package.nix').read_text(),'default-preserves-store-context')
    wrapper=package/'bin/mrjam-adopt-initial-rules'
    require(wrapper.read_text()==('#!/nix/store/rzl7zd3zx56vl7m55x1l49sr4xx2bb7y-bash-5.3p9/bin/bash\n'
        'exec /nix/store/xqnbm0vgqcq9b1b54c80qj9s0qhbwa08-python3-3.13.15/bin/python3 -I -S -B "'+str(package)+
        '/libexec/bootstrap-entry.py" "$@"\n'),'isolated-python-wrapper-exact')
    require(subprocess.run([str(wrapper),'--not-allowed'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False).returncode==64,
        'arguments-refused-before-effect')
    require(not any(p.suffix=='.bundle' for p in package.rglob('*')),'no-private-bundle-in-package')
    metadata=json.loads(subprocess.check_output(['nix','--extra-experimental-features','nix-command','path-info','--json',str(package)]))[str(package)]
    require(str(PROPOSAL) in metadata['references'],'proposal-direct-store-reference-retained')
    closure=set(subprocess.check_output(['nix-store','--query','--requisites',str(package)],text=True).splitlines())
    old=set(subprocess.check_output(['nix-store','--query','--requisites',str(PROPOSAL)],text=True).splitlines())
    require(old<=closure,'all-proposal-transitive-dependencies-retained')
    require(subprocess.run(['nix-store','--verify-path',str(package)],stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode==0,
        'store-path-verified')
    return {'schema_version':1,'result':'PASS','checks':checks,'package':str(package),'store_metadata':metadata,
        'source_files':[{'path':str(p.relative_to(HERE.parents[2])),
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files.values()],
        'limits':['Read-only production packaging checks; no valid entry invocation or production mutation']}


if __name__=='__main__':print(json.dumps(check(sys.argv[1]),indent=2,sort_keys=True))
