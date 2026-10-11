"""Fixture PostgreSQL propre au différentiel, listener loopback vérifié.

Démarrer après préparation des outils : aucun port/service partagé entre suites,
aucune confiance dans un healthcheck antérieur ou une base fournie par l'appelant.
"""
import json
import os
import socket
import subprocess
import time
import uuid

IMAGE='mirror.gcr.io/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'


def main():
    env=dict(os.environ)
    for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(k,None)
    def docker(*args):
        return subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],
                              env=env,check=True,capture_output=True,text=True).stdout
    nom='mrjam-matheval-differentiel-'+uuid.uuid4().hex[:12]
    docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432',
           '--env','POSTGRES_HOST_AUTH_METHOD=trust','--env','POSTGRES_DB=postgres',
           '--label','mrjam.qualification=monolithe-20261011',IMAGE)
    try:
        c=json.loads(docker('inspect',nom))[0]
        port=c['NetworkSettings']['Ports']['5432/tcp'][0]
        assert port['HostIp']=='127.0.0.1'
        for _ in range(150):
            try:
                docker('exec',nom,'pg_isready','--host=127.0.0.1','-U','postgres')
                # La sonde interne ne prouve pas le mapping depuis le test hôte.
                with socket.create_connection(('127.0.0.1',int(port['HostPort'])),timeout=1):pass
                break
            except (subprocess.CalledProcessError,OSError):time.sleep(.1)
        else:raise AssertionError('PostgreSQL local et mapping non prêts')
        env['TEST_DATABASE_URL']='postgres://postgres@127.0.0.1:'+port['HostPort']+'/postgres'
        subprocess.run(['node','tests/matheval-composant.mjs'],env=env,check=True)
    finally:docker('rm','--force',nom)


if __name__=='__main__':main()
