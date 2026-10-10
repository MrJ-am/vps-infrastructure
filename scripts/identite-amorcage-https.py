"""Vérifier publiquement l'issuer et les refus, sans compte ni jeton."""
import json
import ssl
import sys
import urllib.error
import urllib.request

ORIGINE = 'https://log.mrj.am'
ISSUER = ORIGINE + '/realms/mrjam'


class SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def demander(opener, origine, chemin, *, headers=None, data=None):
    req = urllib.request.Request(origine + chemin, headers=headers or {}, data=data)
    try: response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as e: response = e
    with response:
        body = response.read(2097153)
        if len(body) > 2097152: raise ValueError('Réponse publique trop volumineuse')
        return response.code, response.headers, body


def verifier(opener, origine=ORIGINE, *, demander_fn=None):
    lire=demander_fn or demander
    issuer = origine + '/realms/mrjam'
    chemin = '/realms/mrjam/.well-known/openid-configuration'
    for headers in ({}, {'X-Forwarded-Host': 'exemple.invalid',
            'X-Forwarded-Proto': 'http', 'X-Forwarded-Port': '80',
            'X-Forwarded-Prefix': '/injection', 'Forwarded': 'host=exemple.invalid;proto=http'}):
        code, entetes, body = lire(opener, origine, chemin, headers=headers)
        info = json.loads(body)
        if code != 200 or info.get('issuer') != issuer: raise ValueError('Issuer différent')
        for nom in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
            if not info.get(nom, '').startswith(issuer + '/'):
                raise ValueError('Endpoint hors issuer')
        if entetes.get('Referrer-Policy') != 'no-referrer' or 'max-age=31536000' not in entetes.get('Strict-Transport-Security', ''):
            raise ValueError('En-têtes de confidentialité absents')
    code, _, body = lire(opener, origine, '/realms/mrjam/protocol/openid-connect/certs')
    keys = json.loads(body).get('keys', [])
    if code != 200 or not keys or any(not k.get('kid') or set(k) & {'d', 'p', 'q', 'dp', 'dq', 'qi', 'k'} for k in keys):
        raise ValueError('Clés publiques absentes ou privées')
    for chemin in ('/', '/admin/', '/admin/master/console/', '/realms/master/.well-known/openid-configuration',
            '/realms/master/protocol/openid-connect/token', '/metrics', '/health',
            '/realms/mrjam/clients-registrations', '/realms/mrjam/clients-registrations/',
            '/realms/mrjam/clients-registrations/default'):
        if lire(opener, origine, chemin)[0] != 404:
            raise ValueError('Route réservée publiquement accessible')
    if lire(opener, origine, '/realms/mrjam/clients-registrations/default',
            headers={'Content-Type': 'application/json'}, data=b'{}')[0] != 404:
        raise ValueError('Enregistrement dynamique accessible')
    code, _, body = lire(opener, origine, '/code-source/services-mrjam.tar.gz')
    if code != 200 or not body.startswith(b'\x1f\x8b'):
        raise ValueError('Offre de sources indisponible')
    return dict(https=True, issuer_canonique=True, proxy_falsifie_sans_effet=True,
        master_admin_refuses=True, enregistrement_dynamique_refuse=True,
        cles_publiques=True, sources_agpl=True, compte_utilise=False)


if __name__ == '__main__':
    try:
        context = ssl.create_default_context(); context.minimum_version = ssl.TLSVersion.TLSv1_2
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), SansRedirection())
        print(json.dumps(verifier(opener)))
    except Exception:
        sys.exit('Qualification HTTPS refusée ; aucune réponse privée affichée.')
