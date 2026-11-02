#!/usr/bin/env python3
"""Ephemeral human WebAuthn entry; never exports administrative credentials."""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import resource
import secrets
import signal
import socket
import ssl
import struct
import subprocess
import sys
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

ORIGIN = 'https://log.mrj.am'
PREFIX = '/_mrjam-worker-provision/'
DIRECTORY = Path('/run/mrjam-kanidm-worker-login')
SOCKET = Path('/run/mrjam-kanidm-passkey-portal/http.sock')
UNIT = 'mrjam-kanidm-worker-provision.service'
NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
OPAQUE = re.compile(r'[A-Za-z0-9_-]{43}')
TOKEN = re.compile(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
KID = re.compile(r'[A-Za-z0-9:_-]{1,128}')
ROOT = Path(__file__).resolve().parent


class Refused(Exception):
    pass


def require(value):
    if not value:
        raise Refused()


def encode(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()


def decode(raw):
    require(isinstance(raw, bytes) and len(raw) <= 65536)
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out)
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(Refused()))


def unb64(value, maximum=65536):
    require(isinstance(value, str) and len(value) <= maximum and re.fullmatch(r'[A-Za-z0-9_-]+', value))
    raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    require(base64.urlsafe_b64encode(raw).rstrip(b'=').decode() == value)
    return raw


class Loopback(http.client.HTTPSConnection):
    def connect(self):
        sock = socket.create_connection(('127.0.0.1', self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname='log.mrj.am')
        except BaseException:
            sock.close()
            raise


class Api:
    """Only authentication, verification and revocation; no worker/admin API."""
    def __init__(self, ca, digest, port=8443):
        require(hashlib.sha256(ca).hexdigest() == digest)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=ca.decode('ascii'))
        self.port = port

    def __call__(self, method, path, body=None, session=None, token=None):
        if method == 'POST':
            require(path == '/v1/auth' and token is None and isinstance(body, dict) and set(body) == {'step'})
            step = body['step']
            require(isinstance(step, dict) and len(step) == 1)
            if 'init2' in step:
                item = step['init2']
                require(isinstance(item, dict) and set(item) == {'username', 'issue', 'privileged'})
                require(NAME.fullmatch(item['username']) and item['issue'] == 'token' and item['privileged'] is True and session is None)
            elif 'begin' in step:
                require(step['begin'] == 'passkey' and session is not None)
            else:
                require(set(step) == {'cred'} and isinstance(step['cred'], dict) and set(step['cred']) == {'passkey'} and session is not None)
        else:
            require(method == 'GET' and body is None and session is None)
            require(path in ('/v1/self', '/v1/logout') or (path.startswith('/v1/jwk/') and KID.fullmatch(path[8:])))
            require((token is not None) == (path in ('/v1/self', '/v1/logout')))
        headers = {'Host': 'log.mrj.am', 'Accept': 'application/json', 'Content-Type': 'application/json', 'Connection': 'close'}
        if session is not None:
            require(isinstance(session, str) and len(session) <= 4096 and TOKEN.fullmatch(session))
            headers['x-kanidm-auth-session-id'] = session
        if token is not None:
            require(isinstance(token, str) and len(token) <= 16384 and TOKEN.fullmatch(token))
            headers['Authorization'] = 'Bearer ' + token
        peer = Loopback('log.mrj.am', port=self.port, timeout=5, context=self.context)
        try:
            peer.request(method, path, body=None if body is None else encode(body), headers=headers)
            response = peer.getresponse()
            raw = response.read(65537)
            if path == '/v1/logout' and response.status == 401:
                # Already revoked/expired is a closed session, including the
                # unit's successful revocation immediately before this call.
                return {'revoked': True}, None
            require(response.status == 200 and response.getheader('Location') is None)
            require(response.getheader('Content-Type', '').split(';')[0] == 'application/json')
            return decode(raw), response.getheader('x-kanidm-auth-session-id')
        finally:
            peer.close()


def verified_cache(api, token, name, started):
    """New protocol-issued session, validated against the pinned server JWK."""
    require(isinstance(token, str) and len(token) <= 16384 and TOKEN.fullmatch(token))
    header_part, claims_part, signature_part = token.split('.')
    header = decode(unb64(header_part, 4096))
    require(isinstance(header, dict) and header.get('alg') == 'ES256' and isinstance(header.get('kid'), str))
    require(KID.fullmatch(header['kid']) and not any(key in header for key in ('crit', 'jku', 'x5u', 'jwk')))
    key, _ = api('GET', '/v1/jwk/' + header['kid'])
    require(isinstance(key, dict) and key.get('kty') == 'EC' and key.get('crv') == 'P-256' and 'd' not in key)
    x, y = unb64(key.get('x'), 128), unb64(key.get('y'), 128)
    signature = unb64(signature_part, 128)
    require(len(x) == len(y) == 32 and len(signature) == 64)
    public = ec.EllipticCurvePublicNumbers(int.from_bytes(x, 'big'), int.from_bytes(y, 'big'), ec.SECP256R1()).public_key()
    public.verify(utils.encode_dss_signature(int.from_bytes(signature[:32], 'big'), int.from_bytes(signature[32:], 'big')),
                  (header_part + '.' + claims_part).encode(), ec.ECDSA(hashes.SHA256()))
    claims = decode(unb64(claims_part, 16384))
    require(isinstance(claims, dict) and claims.get('spn') == name.lower() + '@log.mrj.am')
    now = int(time.time())
    require(type(claims.get('issued_at')) is int and started - 5 <= claims['issued_at'] <= now + 5)
    require(type(claims.get('expiry')) is int and now + 150 < claims['expiry'] <= started + 3610)
    purpose = claims.get('purpose')
    require(isinstance(purpose, dict) and set(purpose) == {'readwrite'})
    require(isinstance(purpose['readwrite'], dict) and purpose['readwrite'].get('expiry') == claims['expiry'])
    who, _ = api('GET', '/v1/self', token=token)
    require(isinstance(who, dict) and isinstance(who.get('youare'), dict))
    require(who['youare'].get('attrs', {}).get('spn') == [claims['spn']])
    return encode({'instances': {'': {'keys': {header['kid']: key}, 'tokens': {claims['spn']: token}}}})


class Delivery:
    def __init__(self, systemctl):
        require(isinstance(systemctl, str) and systemctl.startswith('/nix/store/') and systemctl.endswith('/bin/systemctl'))
        self.systemctl = systemctl

    def __call__(self, identity, access):
        # Refuse an existing login directory; never clean another login's files.
        DIRECTORY.mkdir(mode=0o700)
        try:
            for name, raw in (('identity.json', identity), ('access.json', access)):
                require(len(raw) <= 65536)
                fd = os.open(DIRECTORY / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                try:
                    require(os.write(fd, raw) == len(raw))
                    os.fsync(fd)
                finally:
                    os.close(fd)
            completed = subprocess.run([self.systemctl, 'start', UNIT], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=145, check=False,
                env={'PATH': str(Path(self.systemctl).parent), 'LANG': 'C.UTF-8'})
            require(completed.returncode == 0)
        finally:
            for name in ('identity.json', 'access.json'):
                try:
                    (DIRECTORY / name).unlink()
                except FileNotFoundError:
                    pass
            DIRECTORY.rmdir()


class Portal:
    def __init__(self, api, delivery):
        self.api = api
        self.delivery = delivery
        self.transactions = {}
        self.created = time.monotonic()
        self.requests = 0
        self.committed = False

    def revoke(self, transaction):
        pending = []
        for token in set(transaction.get('tokens', [])):
            try:
                self.api('GET', '/v1/logout', token=token)
            except Exception:
                pending.append(token)
        transaction['tokens'] = pending
        transaction['caches'] = []
        transaction['session'] = None
        return not pending

    def cleanup(self):
        clean = True
        for transaction in self.transactions.values():
            clean = self.revoke(transaction) and clean
        return clean

    def expire(self):
        for key, transaction in list(self.transactions.items()):
            if time.monotonic() > transaction['deadline']:
                if self.revoke(transaction):
                    del self.transactions[key]
                else:
                    transaction['stage'] = 'refused'
                    transaction['deadline'] = time.monotonic() + 5

    def challenge(self, transaction):
        name = transaction['names'][len(transaction['tokens'])]
        value, session = self.api('POST', '/v1/auth', {'step': {'init2': {'username': name, 'issue': 'token', 'privileged': True}}})
        require(isinstance(value, dict) and 'passkey' in value.get('state', {}).get('choose', []))
        value, session = self.api('POST', '/v1/auth', {'step': {'begin': 'passkey'}}, session=session)
        allowed = value.get('state', {}).get('continue', [])
        require(isinstance(allowed, list) and len(allowed) == 1 and set(allowed[0]) == {'passkey'})
        challenge = allowed[0]['passkey']
        require(isinstance(challenge, dict) and set(challenge) == {'publicKey'})
        public = challenge['publicKey']
        require(isinstance(public, dict) and public.get('rpId') == 'log.mrj.am')
        require(len(unb64(public.get('challenge'), 1024)) >= 16)
        transaction['session'] = session
        transaction['challenge'] = public['challenge']
        transaction['stage'] = 'assertion'
        return {'status': 'PASSKEY_REQUIRED', 'account': len(transaction['tokens']) + 1, 'challenge': challenge}

    def act(self, action, body):
        self.expire()
        self.requests += 1
        require(self.requests <= 80 and time.monotonic() < self.created + 900)
        require(isinstance(body, dict))
        if action == 'begin':
            require(not self.committed and len(self.transactions) < 4 and set(body) == {'identity', 'access'})
            require(isinstance(body['identity'], str) and NAME.fullmatch(body['identity']))
            require(body['access'] is None or (isinstance(body['access'], str) and NAME.fullmatch(body['access'])))
            names = [body['identity']]
            if body['access'] is not None and body['access'].lower() != body['identity'].lower():
                names.append(body['access'])
            transaction = {'names': names, 'tokens': [], 'caches': [], 'started': int(time.time()),
                           'deadline': time.monotonic() + 300, 'stage': 'begin', 'attempts': 0}
            nonce = secrets.token_urlsafe(32)
            self.transactions[nonce] = transaction
            try:
                return {**self.challenge(transaction), 'transaction': nonce}
            except BaseException:
                self.revoke(transaction)
                del self.transactions[nonce]
                raise
        require(isinstance(body.get('transaction'), str) and OPAQUE.fullmatch(body['transaction']))
        transaction = self.transactions.get(body['transaction'])
        require(transaction is not None)
        try:
            if action == 'cancel':
                require(set(body) == {'transaction'})
                require(self.revoke(transaction))
                transaction['stage'] = 'cancelled'
                return {'status': 'CANCELLED'}
            if action == 'assert':
                require(set(body) == {'transaction', 'assertion'} and transaction['stage'] == 'assertion')
                transaction['attempts'] += 1
                require(transaction['attempts'] <= 2)
                assertion = body['assertion']
                require(isinstance(assertion, dict) and set(assertion) == {'id', 'rawId', 'type', 'response'})
                require(assertion['type'] == 'public-key' and assertion['id'] == assertion['rawId'])
                require(1 <= len(unb64(assertion['rawId'], 4096)) <= 1024)
                response = assertion['response']
                require(isinstance(response, dict) and set(response) == {'authenticatorData', 'clientDataJSON', 'signature', 'userHandle'})
                client = decode(unb64(response['clientDataJSON'], 8192))
                require(client.get('type') == 'webauthn.get' and client.get('origin') == ORIGIN
                        and client.get('challenge') == transaction['challenge'] and client.get('crossOrigin', False) is False)
                require(37 <= len(unb64(response['authenticatorData'], 4096)) <= 2048)
                require(8 <= len(unb64(response['signature'], 4096)) <= 1024)
                require(response['userHandle'] is None or len(unb64(response['userHandle'], 1024)) <= 128)
                value, _ = self.api('POST', '/v1/auth', {'step': {'cred': {'passkey': assertion}}}, session=transaction['session'])
                token = value.get('state', {}).get('success')
                require(isinstance(token, str) and TOKEN.fullmatch(token))
                transaction['tokens'].append(token)
                cache = verified_cache(self.api, token, transaction['names'][len(transaction['tokens']) - 1], transaction['started'])
                transaction['caches'].append(cache)
                transaction['session'] = None
                if len(transaction['tokens']) < len(transaction['names']):
                    return self.challenge(transaction)
                transaction['stage'] = 'ready'
                return {'status': 'READY'}
            require(action == 'commit' and set(body) == {'transaction'} and transaction['stage'] == 'ready' and not self.committed)
            self.committed = True
            transaction['stage'] = 'running'
            identity = transaction['caches'][0]
            access = transaction['caches'][-1]
            self.delivery(identity, access)
            # The provisioner revokes its sessions. A fresh logout call is
            # idempotent on the provider; cleanup also covers failed starts.
            require(self.revoke(transaction))
            transaction['stage'] = 'complete'
            return {'status': 'COMPLETE'}
        except BaseException:
            self.revoke(transaction)
            transaction['stage'] = 'refused'
            raise


def request(conn):
    """One bounded HTTP/1 request; never forwards browser headers upstream."""
    deadline = time.monotonic() + 5
    data = b''
    def receive(count):
        remaining = deadline - time.monotonic()
        require(remaining > 0)
        conn.settimeout(remaining)
        chunk = conn.recv(count)
        require(chunk)
        return chunk
    while b'\r\n\r\n' not in data:
        require(len(data) < 8192)
        data += receive(min(1024, 8192 - len(data)))
    head, raw = data.split(b'\r\n\r\n', 1)
    lines = head.split(b'\r\n')
    require(len(lines[0]) <= 4096 and len(lines) <= 41)
    method, target, version = lines[0].decode('ascii').split(' ')
    require(version in ('HTTP/1.0', 'HTTP/1.1') and method in ('GET', 'POST'))
    headers = {}
    for line in lines[1:]:
        name, value = line.decode('ascii').split(':', 1)
        name = name.lower()
        require(re.fullmatch(r'[a-z0-9-]+', name) and name not in headers)
        require(not any(ord(char) < 32 and char != '\t' for char in value))
        headers[name] = value.strip()
    require(headers.get('host') == 'log.mrj.am' and 'transfer-encoding' not in headers)
    require(headers.get('sec-fetch-site', 'same-origin') in ('same-origin', 'none'))
    require('expect' not in headers and not any(ch in target for ch in ('?', '#', '%', '\\')))
    if method == 'GET':
        require(headers.get('content-length', '0') == '0' and not raw)
        require(target in (PREFIX, PREFIX + 'portal.js', PREFIX + 'style.css'))
        return method, target, None
    require(headers.get('origin') == ORIGIN and headers.get('content-type') == 'application/json')
    require(re.fullmatch(r'[0-9]{1,5}', headers.get('content-length', '')))
    length = int(headers['content-length'])
    require(2 <= length <= 32768 and target in {PREFIX + 'api/' + a for a in ('begin', 'assert', 'commit', 'cancel')})
    require(len(raw) <= length)
    while len(raw) < length:
        raw += receive(length - len(raw))
    require(len(raw) == length)
    return method, target, decode(raw)


def respond(conn, status, content_type, raw):
    csp = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    headers = f'HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(raw)}\r\nConnection: close\r\nCache-Control: no-store\r\nContent-Security-Policy: {csp}\r\nReferrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\n\r\n'
    conn.sendall(headers.encode() + raw)


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    require(len(sys.argv) == 1 and os.geteuid() == 0)
    public = decode((ROOT / 'public.json').read_bytes())
    require(set(public) == {'ca_sha256', 'systemctl'})
    api = Api((ROOT / 'ca.pem').read_bytes(), public['ca_sha256'])
    portal = Portal(api, Delivery(public['systemctl']))
    nginx = pwd.getpwnam('nginx')
    SOCKET.parent.mkdir(mode=0o750)
    os.chown(SOCKET.parent, 0, nginx.pw_gid)
    os.chmod(SOCKET.parent, 0o750)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    clean = True
    stopping = False
    def stop(*_):
        nonlocal stopping
        # Complete an already started fixed unit before revoking its sessions.
        # SIGTERM must not race provisioning by killing its systemctl waiter.
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        listener.bind(str(SOCKET))
        os.chown(SOCKET, 0, nginx.pw_gid)
        os.chmod(SOCKET, 0o660)
        listener.listen(4)
        listener.settimeout(1)
        while not stopping and time.monotonic() < portal.created + 900 and portal.requests < 80:
            portal.expire()
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            with conn:
                try:
                    _, uid, _ = struct.unpack('3i', conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
                    require(uid in (0, nginx.pw_uid))
                    method, target, body = request(conn)
                    if method == 'GET':
                        filename, media = {'': ('index.html', 'text/html; charset=utf-8'), 'portal.js': ('portal.js', 'text/javascript; charset=utf-8'), 'style.css': ('style.css', 'text/css; charset=utf-8')}[target[len(PREFIX):]]
                        respond(conn, '200 OK', media, (ROOT / filename).read_bytes())
                    else:
                        result = portal.act(target.rsplit('/', 1)[-1], body)
                        if result['status'] == 'COMPLETE':
                            print('PASSKEY_PORTAL_PREPARED', flush=True)
                        respond(conn, '200 OK', 'application/json', encode(result))
                except Exception:
                    try:
                        respond(conn, '400 Bad Request', 'application/json', encode({'status': 'REFUSED'}))
                    except Exception:
                        pass
    finally:
        clean = portal.cleanup()
        listener.close()
        SOCKET.unlink(missing_ok=True)
        SOCKET.parent.rmdir()
    print('PASSKEY_PORTAL_CLOSED' if clean else 'PASSKEY_PORTAL_CLEANUP_REQUIRED')
    return 0 if clean else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('PASSKEY_PORTAL_REFUSED', file=sys.stderr)
        raise SystemExit(1)
