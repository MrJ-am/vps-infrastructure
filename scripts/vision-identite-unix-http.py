"""Contrôles HTTP synthétiques dans le seul réseau privé de qualification."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
ETAPE = 'demarrage'


def verifier(secret):
    global ETAPE
    # Aucun proxy, redirect ou hôte arbitraire : loopback du namespace visé.
    class SansRedirection(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs): return None
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection())
    def api(path, donnees=None, jeton=None):
        corps = urllib.parse.urlencode(donnees).encode() if donnees else None
        entetes = {'Content-Type': 'application/x-www-form-urlencoded'} if donnees else {}
        if jeton: entetes['Authorization'] = 'Bearer ' + jeton
        with client.open(urllib.request.Request('http://127.0.0.1:8085' + path, corps, entetes), timeout=3) as r:
            return json.loads(r.read(2 * 1024 * 1024))
    ETAPE = 'decouverte'
    for _ in range(120):
        try:
            decouverte = api('/realms/master/.well-known/openid-configuration'); break
        except (OSError, urllib.error.HTTPError): time.sleep(1)
    else: raise RuntimeError('Découverte native indisponible')
    ETAPE = 'issuer'
    assert decouverte['issuer'] == 'http://127.0.0.1:8085/realms/master'
    ETAPE = 'authentification_synthetique'
    jeton = api('/realms/master/protocol/openid-connect/token', dict(
        client_id='admin-cli', username='qualification', password=secret, grant_type='password'))['access_token']
    ETAPE = 'realm'
    realm = api('/admin/realms/master', jeton=jeton)
    assert realm['realm'] == 'master' and realm['registrationAllowed'] is False
    ETAPE = 'version'
    info = api('/admin/serverinfo', jeton=jeton)
    assert info['systemInfo']['version'] == '26.7.3'
    ETAPE = 'spi'
    assert 'mrjam-courriel' in info['providers']['authenticator']['providers']
    return dict(demarrage_optimise=True, version_native=True, spi_charge=True,
        inscription_native_fermee=True, api_synthetique=True)


if __name__ == '__main__':
    # Le mot de passe arrive sur stdin, jamais dans argv, logs ou rapport.
    try:
        secret = json.loads(sys.stdin.read(4096))['secret']
        print(json.dumps(verifier(secret)), flush=True)
    except Exception as e:
        print(json.dumps({'http_synthetique': False, 'etape': ETAPE,
            'type_refus': type(e).__name__ if type(e).__name__ in ('AssertionError', 'KeyError', 'TypeError', 'HTTPError', 'URLError') else 'inconnu'}), file=sys.stderr); sys.exit(1)
