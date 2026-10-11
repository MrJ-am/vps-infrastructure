"""Construire une image neuve puis exercer cet artefact, sans publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from assemblage import chemins_sources, compilation_entrees

ROOT=Path(__file__).resolve().parents[1]


def qualifier(destination, sans_cache=False):
    destination=Path(destination).resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    inputs=compilation_entrees(sources)
    # Le compilateur ne reçoit ni secrets CI, ni configuration de production.
    build_env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','SBCL_HOME','LANG','LC_ALL','MRJAM_ATELIER')}
    build_env.update(MRJAM_EXECUTABLE=str(destination),
                     ASDF_SOURCE_REGISTRY='(:source-registry :ignore-inherited-configuration)')
    env=dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='mrjam-fasl-reference-') as cache:
        metadata=Path(cache)/'construction.json'
        build_env['MRJAM_BUILD_METADATA']=str(metadata)
        if sans_cache:
            build_env['ASDF_OUTPUT_TRANSLATIONS']=f'(:output-translations (t "{cache}/") :ignore-inherited-configuration)'
        debut=time.monotonic()
        subprocess.run([os.environ.get('SBCL','sbcl'),'--script','assemblage/construire.lisp'],cwd=ROOT,env=build_env,check=True)
        construction=time.monotonic()-debut
        fasl_count=len(list(Path(cache).rglob('*.fasl')))
        if sans_cache and not fasl_count:raise AssertionError('Cache de référence non utilisé')
        env['MRJAM_TEST_EXECUTABLE']=str(destination)
        debut=time.monotonic()
        subprocess.run(['node','tests/matheval-composant.mjs'],cwd=ROOT,env=env,check=True)
        resultat={'format':1,'artefact_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                  'taille_octets':destination.stat().st_size,'construction_secondes':round(construction,4),
                  'tests_secondes':round(time.monotonic()-debut,4),'fasl_reference_sans_cache':sans_cache,
                  'fasl_reference_crees':fasl_count,
                  'compilation':json.loads(metadata.read_text()),
                  'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  'sources_lisp_sha256':inputs,
                  'qualification':'locale HTTP/transactions/redemarrage, assemblage complet non qualifie',
                  'publication_autorisee':False}
        if compilation_entrees(sources)!=inputs:raise ValueError('Sources Lisp modifiées pendant la construction/qualification')
        destination.with_suffix('.qualification.json').write_text(json.dumps(resultat,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in resultat.items() if k!='sources_lisp_sha256'},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--destination',default='state/artefacts/mrjam-metier');p.add_argument('--sans-cache',action='store_true')
    a=p.parse_args();qualifier(a.destination,a.sans_cache)
