"""Fixed verifier entry for the isolated Signature resource job.

The caller supplies an already Git-verified read-only source, a fresh disposable
job, and the observed commit. No candidate script or configuration is executed.
"""
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import parisienne
import verify_generated
from consumer_identity import SOURCE_PATHS as SOURCES, INPUTS


def require(value, code):
    if not value:
        raise ValueError(code)


def regular(path):
    require(not any(p.is_symlink() for p in (path,*path.parents)), 'SIGNATURE_SOURCE_LINK_REFUSED')
    info=path.lstat()
    # A verified read-only Nix input may be deduplicated with hardlinks.
    require(stat.S_ISREG(info.st_mode) and 0<info.st_size<=16*1024**2, 'SIGNATURE_SOURCE_FILE_REFUSED')
    return path.read_bytes()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(source, job, revision):
    require(re.fullmatch('[0-9a-f]{40}',revision), 'SIGNATURE_REVISION_REFUSED')
    require(source.is_absolute() and job.is_absolute(), 'SIGNATURE_PATH_REFUSED')
    inputs={name:regular(source/name) for name in sorted(INPUTS)}
    require(sum(map(len,inputs.values()))<=32*1024**2, 'SIGNATURE_SOURCE_SIZE_REFUSED')
    captured=job/'captured';generated=job/'generated';bundle=job/'identity'
    for path in (captured,generated,bundle):
        path.mkdir(mode=0o700)
    for name,raw in inputs.items():
        path=captured/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    for name in ('mrjam.sty','fonts/Parisienne-Regular.ttf','fonts/Parisienne-OFL.txt','artwork/Echologo.svg'):
        path=generated/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(inputs[name])
    (generated/'web').mkdir();(generated/'tools').mkdir()
    support=Path(__file__).resolve().parent
    generator=regular(support/'reference-generator.py')
    provenance=json.loads(regular(support/'generator-provenance.json'))
    require(sha(generator)==provenance['sha256'], 'SIGNATURE_GENERATOR_CHANGED')
    program=generated/'tools/build-web.py';program.write_bytes(generator)
    subprocess.run([sys.executable,'-I',str(program)],check=True,timeout=120,
                   stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                   env={'LANG':'C.UTF-8'})
    verification=verify_generated.verify(captured,generated)
    resources={name:inputs[path] for name,path in SOURCES.items()}
    resources['Parisienne-Regular.woff2'],conversion=parisienne.convert(resources['Parisienne-Regular.ttf'])
    for name,raw in resources.items():
        (bundle/name).write_bytes(raw)
    manifest={'schema_version':1,'revision':revision,'deployment_authorized':False,
              'input_sha256':{name:sha(raw) for name,raw in inputs.items()},
              'resources':{name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in resources.items()},
              'regeneration':verification,'conversion':conversion}
    (bundle/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    require(len(sys.argv)==4,'SIGNATURE_ARGUMENTS_REFUSED')
    build(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
