"""Ancien contrat public Vision exercé sur le transport commun réel."""
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def verifier(socket,sources):
    spec=importlib.util.spec_from_file_location('artefact_http',ROOT/'tests/serveur-artefact.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    def get(path,extra=b'',methode='GET'):
        return h.requete(socket,h.http(methode,path,service='vision',extra=extra))
    attendu=(Path(sources)/'interface/app.html').read_bytes()
    for path in ['/','/docs','/docs/','/privacy','/connexion','/invitation','/admission']:
        status,headers,body=get(path)
        assert status==200 and body==attendu and b'id="application"' in body
        assert b"base-uri 'none'" in headers and b'<base ' not in body
    for entetes in [b'',b'Forwarded: proto=https;host=attaque.test\r\nX-Forwarded-Host: attaque.test\r\n']:
        status,headers,body=get('/mcp-config.json',entetes)
        assert status==200 and json.loads(body)=={'url_mcp':'https://exemple.test/vision/mcp','gestion_acces':'https://exemple.test/vision/auth/mcp'}
        assert b'Cache-Control: no-store' in headers
    assert get('/mcp-config.json',methode='POST')[0]==404
    for path in ['/api/fiches','/mcp']:assert get(path)[0]==401
    print('Vision commun : sept routes publiques, CSP, adresses configurées indépendantes des en-têtes et refus anonyme.')
