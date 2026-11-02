#!/usr/bin/env python3
"""Read-only, closed Kanidm capability probe. Never emits tokens or claims."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import runpy
import socket
import ssl
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
# This is the new, reviewed helper in the same immutable package, not legacy code.
HELPERS = runpy.run_path(str(ROOT/'adapt.py'), run_name='credential_helpers')
Refused = HELPERS['Refused']
INPUT = Path('/run/mrjam-kanidm-capability-probe')
NAMES = ('admission', 'cycle', 'replay')
ACCOUNTS = {'admission':'mrjam-admission', 'cycle':'mrjam-cycle', 'replay':'mrjam-replay'}
PATHS = frozenset(['/v1/self'] + [f'/v1/service_account/{name}/_attr/{attribute}'
                  for name in ('admin', 'idm_admin')
                  for attribute in ('account_expire', 'account_valid_from', 'passkeys')])
TOKEN = re.compile(r'[A-Za-z0-9_.-]{32,4096}')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def parse_json(raw):
    # Reuse strict duplicate/NaN rejection for arbitrary JSON roots too.
    return HELPERS['strict_json'](b'{"value":'+raw+b'}')['value']


def tls_context(ca, expected_hash):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash) or hashlib.sha256(ca).hexdigest() != expected_hash:
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
    if path not in PATHS or not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise Refused()
    peer = Loopback('log.mrj.am', port=port, timeout=5, context=context)
    try:
        peer.request('GET', path, headers={'Host':'log.mrj.am', 'Accept':'application/json',
                                         'Authorization':'Bearer '+token, 'Connection':'close'})
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


def tokens():
    parent = HELPERS['open_directory'](INPUT)
    try:
        HELPERS['private_directory'](parent)
        present = HELPERS['entries'](parent)
        if not present <= set(NAMES):
            raise Refused()
        result = {}
        for name in NAMES:
            if name not in present:
                result[name] = None
                continue
            raw = HELPERS['read_file'](parent, name, 4096, sealed=True)
            value = raw.decode('ascii')
            if value.endswith('\n'):
                value = value[:-1]
            if not TOKEN.fullmatch(value):
                raise Refused()
            result[name] = value
        return result
    finally:
        os.close(parent)


def identity(value, expected):
    if not isinstance(value, dict) or set(value) != {'youare'}:
        return None
    entry = value['youare']
    if not isinstance(entry, dict) or set(entry) != {'attrs'} or not isinstance(entry['attrs'], dict):
        return None
    attrs = entry['attrs']
    classes = attrs.get('class')
    if (attrs.get('name') != [expected] or not isinstance(classes, list)
            or not all(isinstance(v, str) for v in classes) or 'service_account' not in classes):
        return None
    ids = attrs.get('uuid')
    if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not UUID.fullmatch(ids[0]):
        return None
    memberships = attrs.get('memberof')
    if not isinstance(memberships, list) or not all(isinstance(v, str) for v in memberships):
        memberships = []
    def member(name):
        return name in memberships or name+'@log.mrj.am' in memberships
    return {'authenticated_service':True,
            'onboarding_membership':member('idm_people_on_boarding'),
            'mail_read_membership':member('idm_account_mail_read'),
            'people_admin_membership':member('idm_people_admins')}


def expired(value, now):
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], str):
        return False
    text = value[0]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)', text):
        return False
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')) < now
    except ValueError:
        return False


def examine(capabilities, get, now):
    result = {'schema_version':1, 'all_tokens_present':all(capabilities.get(n) for n in NAMES),
              'tokens_distinct':False, 'administrative_prestate_observable':False,
              'builtin_admins_disabled':False, 'write_authorization_proved':False}
    values = [capabilities.get(n) for n in NAMES]
    result['all_tokens_present'] = bool(result['all_tokens_present'])
    result['tokens_distinct'] = result['all_tokens_present'] and len(set(values)) == 3
    authenticated = []
    for name in NAMES:
        state = {'present':capabilities.get(name) is not None, 'authenticated_service':False,
                 'onboarding_membership':False, 'mail_read_membership':False,
                 'people_admin_membership':False}
        token = capabilities.get(name)
        if token is not None:
            found = identity(get(token, '/v1/self'), ACCOUNTS[name])
            if found is not None:
                state.update(found)
                authenticated.append(token)
        result[name] = state
    # Only the fixed technical built-ins, never a person or an unbounded list.
    # Absence/hidden attributes do not establish a safe pre-state.
    for token in authenticated:
        both = []
        for account in ('admin', 'idm_admin'):
            expiry = get(token, f'/v1/service_account/{account}/_attr/account_expire')
            valid_from = get(token, f'/v1/service_account/{account}/_attr/account_valid_from')
            passkeys = get(token, f'/v1/service_account/{account}/_attr/passkeys')
            # A null attribute may mean no access rather than absence. Without
            # a separately qualified administrative reader, do not assert it.
            observable = (isinstance(expiry, list) and len(expiry) == 1
                          and isinstance(valid_from, list) and isinstance(passkeys, list))
            both.append((observable, observable and expired(expiry, now) and not valid_from and not passkeys))
        if all(item[0] for item in both):
            result['administrative_prestate_observable'] = True
            result['builtin_admins_disabled'] = all(item[1] for item in both)
            break
    return result


def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise Refused()
        public = HELPERS['strict_json']((ROOT/'probe-public.json').read_bytes())
        if set(public) != {'ca_sha256'}:
            raise Refused()
        context = tls_context((ROOT/'ca.pem').read_bytes(), public['ca_sha256'])
        result = examine(tokens(), lambda token,path: request(token,path,context), datetime.now(timezone.utc))
        print(json.dumps(result, separators=(',', ':'), sort_keys=True))
    except Exception:
        print('{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
