"""Ancienne suite Node conservée comme référence sur une base jetable indépendante."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemblage import chemins_sources

nom='mrjam-matheval-reference-'+uuid.uuid4().hex[:12]
image='mirror.gcr.io/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL')}
def docker(*args):return subprocess.check_output(['docker',*args],env=env,text=True)
docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432','--env','POSTGRES_HOST_AUTH_METHOD=trust','--env','POSTGRES_DB=matheval_reference_test',image)
try:
    port=json.loads(docker('inspect',nom))[0]['NetworkSettings']['Ports']['5432/tcp'][0]
    assert port['HostIp']=='127.0.0.1'
    for _ in range(100):
        try:docker('exec',nom,'pg_isready','--host=127.0.0.1','-U','postgres');break
        except subprocess.CalledProcessError:time.sleep(.1)
    else:raise AssertionError('PostgreSQL référence indisponible')
    env['TEST_DATABASE_URL']='postgres://postgres@127.0.0.1:'+port['HostPort']+'/matheval_reference_test'
    subprocess.run(['npm','--prefix',chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))['matheval']/'server','test'],env=env,check=True)
finally:docker('rm','--force',nom)
