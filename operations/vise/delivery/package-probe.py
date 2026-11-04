"""Synthetic runtime qualification of a fixed packaged ViSe, without rebuilding."""
import hashlib,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stage import Build
from runtime_stage import Runtime
import source_policy as P

def main():
    P.require(sys.argv[1:]==['/input'],'VISE_PROBE_ARGUMENTS_REFUSED')
    b=Build(json.loads(Path('@runtime@').read_bytes()))
    b.policy=P.checked_policy(P.read_json(Path(b.runtime['policy'])))
    sources,b.proposal=P.verify_sources(Path('/input'),b.policy,Path(b.runtime['tree_gate']))
    b.source=Path('/input')/sources['vise']['root']
    package=Path('@package@');manifest=P.read_json(package/'artifact.json')
    P.require(manifest['profile']=='vise-v1' and manifest['proposal_sha256']==b.proposal
        and manifest['deployment_authorized'] is False,'VISE_PACKAGE_BINDING_REFUSED')
    payload=Path(manifest['server'])/'libexec/mrjam-server'
    P.require(hashlib.sha256(P.read(payload,64*1024**2)).hexdigest()==manifest['server_sha256'],
        'VISE_PACKAGE_SERVER_CHANGED')
    b.server=package/'server';b.dist=package/'dist'
    observed={}
    for path in b.dist.rglob('*'):
        if path.is_dir():continue
        name=P.relative(str(path.relative_to(b.dist)))
        observed[name]=hashlib.sha256(P.read(path,64*1024**2)).hexdigest()
    P.require(observed==manifest['frontend_files'],'VISE_PACKAGE_FRONTEND_CHANGED')
    shutil.copytree(b.source,b.job/'project')
    Runtime(b).run()
    print(json.dumps({'scope':'isolated-packaged-runtime-only','package':str(package),
        'proposal_sha256':b.proposal,'steps':b.steps,'production_access':False,
        'deployment_authorized':False},sort_keys=True),file=sys.stderr)

if __name__=='__main__':
    try:main()
    except Exception as error:
        import re
        code=str(error) if re.fullmatch('VISE_[A-Z_]+',str(error)) else 'VISE_PACKAGE_PROBE_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1) from None
