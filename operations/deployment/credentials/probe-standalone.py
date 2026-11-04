#!/usr/bin/env python3
"""Generated closed stdin probe. No mutation; no imports from cwd; no secret output."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import resource
import signal
import socket
import ssl
import stat
import sys
from datetime import datetime, timezone

class Refused(Exception):
    """Only a fixed error code may escape the executable."""

def strict_json(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 65536:
        raise Refused()

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refused()
            result[key] = value
        return result

    def constant(_):
        raise Refused()
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs, parse_constant=constant)
    if type(value) is not dict:
        raise Refused()
    return value

def open_directory(path):
    path = Path(path)
    if not path.is_absolute() or any((p in ('.', '..') for p in str(path).split('/'))):
        raise Refused()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise

def read_file(directory, name, maximum, *, sealed=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        expected_mode = 288 if sealed else 384
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid() or (stat.S_IMODE(before.st_mode) != expected_mode) or (not 1 <= before.st_size <= maximum):
            raise Refused()
        if sealed and (before.st_gid != 0 or not os.fstatvfs(fd).f_flag & os.ST_RDONLY):
            raise Refused()
        chunks = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise Refused()
        result = b''.join(chunks)
        if len(result) != before.st_size:
            raise Refused()
        return result
    finally:
        os.close(fd)

HELPERS = {'strict_json':strict_json}

NAMES = ('admission', 'cycle', 'replay')

ACCOUNTS = {'admission': 'mrjam-admission', 'cycle': 'mrjam-cycle', 'replay': 'mrjam-replay'}

PATHS = frozenset(['/v1/self'] + [f'/v1/service_account/{name}/_attr/{attribute}' for name in ('admin', 'idm_admin') for attribute in ('account_expire', 'account_valid_from', 'passkeys')])

TOKEN = re.compile('[A-Za-z0-9_.-]{32,4096}')

UUID = re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')

def parse_json(raw):
    return HELPERS['strict_json'](b'{"value":' + raw + b'}')['value']

def tls_context(ca, expected_hash):
    if not re.fullmatch('[0-9a-f]{64}', expected_hash) or hashlib.sha256(ca).hexdigest() != expected_hash:
        raise Refused()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cadata=ca.decode('ascii'))
    return ctx

class Loopback(http.client.HTTPSConnection):

    def connect(self):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        try:
            self.sock = self._context.wrap_socket(stream, server_hostname='log.mrj.am')
        except Exception:
            stream.close()
            raise

def request(token, path, context, *, port=8443):
    if path not in PATHS or not isinstance(token, str) or (not TOKEN.fullmatch(token)):
        raise Refused()
    peer = Loopback('log.mrj.am', port=port, timeout=5, context=context)
    try:
        peer.request('GET', path, headers={'Host': 'log.mrj.am', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token, 'Connection': 'close'})
        response = peer.getresponse()
        raw = response.read(65537)
        if len(raw) > 65536:
            raise Refused()
        if response.status in (401, 403, 404):
            return None
        if response.status != 200 or response.getheader('Location') is not None:
            raise Refused()
        if response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise Refused()
        return parse_json(raw)
    finally:
        peer.close()

def identity(value, expected):
    if not isinstance(value, dict) or set(value) != {'youare'}:
        return None
    entry = value['youare']
    if not isinstance(entry, dict) or set(entry) != {'attrs'} or (not isinstance(entry['attrs'], dict)):
        return None
    attrs = entry['attrs']
    classes = attrs.get('class')
    if attrs.get('name') != [expected] or not isinstance(classes, list) or (not all((isinstance(v, str) for v in classes))) or ('service_account' not in classes):
        return None
    ids = attrs.get('uuid')
    if not isinstance(ids, list) or len(ids) != 1 or (not isinstance(ids[0], str)) or (not UUID.fullmatch(ids[0])):
        return None
    memberships = attrs.get('memberof')
    if not isinstance(memberships, list) or not all((isinstance(v, str) for v in memberships)):
        memberships = []

    def member(name):
        return name in memberships or name + '@log.mrj.am' in memberships
    return {'authenticated_service': True, 'onboarding_membership': member('idm_people_on_boarding'), 'mail_read_membership': member('idm_account_mail_read'), 'people_admin_membership': member('idm_people_admins')}

def expired(value, now):
    if not isinstance(value, list) or len(value) != 1 or (not isinstance(value[0], str)):
        return False
    text = value[0]
    if not re.fullmatch('\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,9})?(?:Z|\\+00:00)', text):
        return False
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')) < now
    except ValueError:
        return False

def examine(capabilities, get, now):
    result = {'schema_version': 1, 'all_tokens_present': all((capabilities.get(n) for n in NAMES)), 'tokens_distinct': False, 'administrative_prestate_observable': False, 'builtin_admins_disabled': False, 'write_authorization_proved': False}
    values = [capabilities.get(n) for n in NAMES]
    result['all_tokens_present'] = bool(result['all_tokens_present'])
    result['tokens_distinct'] = result['all_tokens_present'] and len(set(values)) == 3
    authenticated = []
    for name in NAMES:
        state = {'present': capabilities.get(name) is not None, 'authenticated_service': False, 'onboarding_membership': False, 'mail_read_membership': False, 'people_admin_membership': False}
        token = capabilities.get(name)
        if token is not None:
            found = identity(get(token, '/v1/self'), ACCOUNTS[name])
            if found is not None:
                state.update(found)
                authenticated.append(token)
        result[name] = state
    for token in authenticated:
        both = []
        for account in ('admin', 'idm_admin'):
            expiry = get(token, f'/v1/service_account/{account}/_attr/account_expire')
            valid_from = get(token, f'/v1/service_account/{account}/_attr/account_valid_from')
            passkeys = get(token, f'/v1/service_account/{account}/_attr/passkeys')
            observable = isinstance(expiry, list) and len(expiry) == 1 and isinstance(valid_from, list) and isinstance(passkeys, list)
            both.append((observable, observable and expired(expiry, now) and (not valid_from) and (not passkeys)))
        if all((item[0] for item in both)):
            result['administrative_prestate_observable'] = True
            result['builtin_admins_disabled'] = all((item[1] for item in both))
            break
    return result

PUBLIC_CA = b'-----BEGIN CERTIFICATE-----\nMIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\nTzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\ncmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\nWhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\nZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\nMTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\nh77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U\nA5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW\nT8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH\nB5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC\nB5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv\nKBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn\nOlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn\njh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw\nqHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI\nrU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV\nHRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq\nhkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL\nubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ\n3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK\nNFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5\nORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur\nTkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC\njNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc\noyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq\n4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA\nmRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d\nemyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\nMIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw\nCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg\nR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00\nMDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT\nZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw\nEAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW\n+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9\nItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T\nAQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI\nzj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW\ntL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1\n/q4AaOeMSQ+2b1tbFfLn\n-----END CERTIFICATE-----\n'
PUBLIC_CA_SHA256 = '0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0'

def standalone_tokens():
    result = {name:None for name in NAMES}
    parent = open_directory('/var/lib/mrjam-identite')
    try:
        meta = os.fstat(parent)
        if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
            raise Refused()
        for name in NAMES:
            try:
                raw = read_file(parent, 'kanidm-'+name+'.token', 4096)
            except FileNotFoundError:
                continue
            value = raw.decode('ascii')
            if value.endswith('\n'):
                value = value[:-1]
            if not TOKEN.fullmatch(value):
                raise Refused()
            result[name] = value
        return result
    finally:
        os.close(parent)

def deadline(_signal, _frame):
    raise Refused()

def main():
    previous = None
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise Refused()
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        previous = signal.signal(signal.SIGALRM, deadline)
        signal.alarm(120)
        context = tls_context(PUBLIC_CA, PUBLIC_CA_SHA256)
        result = examine(standalone_tokens(), lambda token,path: request(token,path,context), datetime.now(timezone.utc))
        print(json.dumps(result, separators=(',', ':'), sort_keys=True))
    except Exception:
        print('{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}', file=sys.stderr)
        return 1
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
