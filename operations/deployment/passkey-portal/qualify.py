#!/usr/bin/env python3
"""Real disposable Kanidm + cryptographically signed software passkeys only."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import secrets
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fido2.cose import ES256
from fido2.webauthn import AttestationObject, AttestedCredentialData, AuthenticatorData

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('candidate', ROOT / 'portal.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
F = runpy.run_path(str(ROOT.parent / 'credentials' / 'qualify_provision.py'), run_name='fixture')
P = F['P']
RESULT = runpy.run_path(str(ROOT / 'result_probe.py'), run_name='result_probe_fixture')


def check(value, label):
    if not value:
        raise RuntimeError(label)


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class SoftwarePasskey:
    """Real P-256 signing; never shipped in the production portal package."""
    def __init__(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.id = secrets.token_bytes(32)
        self.counter = 0

    def register(self, challenge):
        public = challenge['publicKey']
        client = C.encode({'type':'webauthn.create', 'challenge':public['challenge'], 'origin':C.ORIGIN, 'crossOrigin':False})
        credential = AttestedCredentialData.create(bytes(16), self.id, ES256.from_cryptography_key(self.private.public_key()))
        data = AuthenticatorData.create(hashlib.sha256(public['rp']['id'].encode()).digest(),
            AuthenticatorData.FLAG.UP | AuthenticatorData.FLAG.UV | AuthenticatorData.FLAG.AT, 0, credential)
        attestation = AttestationObject.create('none', data, {})
        return {'id':b64(self.id),'rawId':b64(self.id),'type':'public-key',
                'response':{'attestationObject':b64(attestation),'clientDataJSON':b64(client),'transports':['internal']},
                'extensions':{}}

    def assertion(self, challenge, *, tamper=False, origin=C.ORIGIN):
        public = challenge['publicKey']
        check(any(item['id'] == b64(self.id) for item in public['allowCredentials']), 'PASSKEY_CHALLENGE_ID')
        self.counter += 1
        client = C.encode({'type':'webauthn.get','challenge':public['challenge'],'origin':origin,'crossOrigin':False})
        data = AuthenticatorData.create(hashlib.sha256(public['rpId'].encode()).digest(),
            AuthenticatorData.FLAG.UP | AuthenticatorData.FLAG.UV, self.counter)
        signature = self.private.sign(bytes(data) + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        if tamper:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        return {'id':b64(self.id),'rawId':b64(self.id),'type':'public-key','response':{
            'authenticatorData':b64(data),'clientDataJSON':b64(client),'signature':b64(signature),'userHandle':None}}


def enroll(f, administrator, name):
    f.ok(administrator, 'POST', '/v1/person', {'attrs':{'name':[name],'displayname':['Invented portal operator']}})
    intent = f.ok(administrator, 'GET', '/v1/person/' + name + '/_credential/_update_intent/600')
    session, _ = f.ok(None, 'POST', '/v1/credential/_exchange_intent', intent['token'])
    state = f.ok(None, 'POST', '/v1/credential/_update', ['passkeyinit', session])
    key = SoftwarePasskey()
    registration = key.register(state['mfaregstate']['Passkey'])
    state = f.ok(None, 'POST', '/v1/credential/_update', [{'passkeyfinish':['Invented software passkey',registration]}, session])
    check(state['can_commit'], 'PASSKEY_ENROLLMENT_COMMITTABLE')
    f.ok(None, 'POST', '/v1/credential/_commit', session)
    return key


def qualify():
    with F['Fixture']() as f:
        identity_admin, access_admin = f.login('idm_admin'), f.login('admin')
        keys = {name:enroll(f, identity_admin, name) for name in ('portal-identity','portal-access')}
        for group in ('idm_admins','idm_access_control_admins'):
            manager = identity_admin if group == 'idm_admins' else access_admin
            code, _, _ = f.request(manager, 'POST', '/v1/group/' + group + '/_attr/member', list(keys))
            check(code == 200, 'FIXTURE_GRANT_' + group + '_' + str(code))
        f.ok(identity_admin,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],
            'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
        f.ok(identity_admin,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
        f.ok(access_admin,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
        admission = f.ok(identity_admin,'POST','/v1/service_account/mrjam-admission/_api_token',
            {'label':'invented-existing-admission','expiry':int(time.time())+86400,'read_write':True})
        files = F['MemoryFiles'](admission)
        ca = (f.root / 'ca.pem').read_bytes()
        api = C.Api(ca, hashlib.sha256(ca).hexdigest(), f.port)
        delivered = []
        def delivery(identity, access):
            first, second = P['cache_token'](identity), P['cache_token'](access)
            check(not P['needs_reauth'](identity) and not P['needs_reauth'](access), 'CACHE_PRIVILEGE_COMPATIBILITY')
            result = P['provision_workers'](P['Api'](f.context, port=f.port), first, second, files, int(time.time()))
            check(result['prepared'], 'V2_REAL_PROVISION')
            delivered.append((first,second))
        portal = C.Portal(api, delivery)
        first = portal.act('begin', {'identity':'portal-identity','access':'portal-access'})
        nonce = first['transaction']
        check(set(first) == {'status','account','challenge','transaction'}, 'BROWSER_ONLY_CHALLENGE')
        second = portal.act('assert', {'transaction':nonce,'assertion':keys['portal-identity'].assertion(first['challenge'])})
        check(second['status'] == 'PASSKEY_REQUIRED' and second['account'] == 2, 'SEPARATE_ACCESS_ACCOUNT')
        result = portal.act('assert', {'transaction':nonce,'assertion':keys['portal-access'].assertion(second['challenge'])})
        check(result == {'status':'READY'}, 'REAL_PASSKEY_SIGNATURES_ACCEPTED')
        result = portal.act('commit', {'transaction':nonce})
        check(result == {'status':'COMPLETE'} and len(delivered) == 1, 'REAL_PROVISION_COMPLETE')
        check(all(f.request(token,'GET','/v1/self')[0] == 401 for token in delivered[0]), 'DEDICATED_SESSIONS_REVOKED')
        check(not portal.transactions[nonce]['tokens'] and not portal.transactions[nonce]['caches'], 'MEMORY_RELEASED')
        try:
            portal.act('commit', {'transaction':nonce})
        except Exception:
            pass
        else:
            raise RuntimeError('COMMIT_REPLAY_ALLOWED')
        # Same-account mode creates one fresh session and idempotently uses v2.
        same = C.Portal(api, delivery)
        first = same.act('begin', {'identity':'portal-identity','access':None})
        nonce = first['transaction']
        check(same.act('assert', {'transaction':nonce,'assertion':keys['portal-identity'].assertion(first['challenge'])}) == {'status':'READY'}, 'SINGLE_ACCOUNT_READY')
        check(same.act('commit', {'transaction':nonce}) == {'status':'COMPLETE'}, 'SINGLE_ACCOUNT_COMPLETE')
        check(delivered[-1][0] == delivered[-1][1], 'SINGLE_FRESH_SESSION')
        observed = RESULT['examine'](P, files.values, lambda token:f.ok(token,'GET','/v1/self'))
        check(observed['all_expected_memberships'] and observed['tokens_distinct']
              and observed['write_authorization_proved'] is False, 'READ_ONLY_RESULT_PROBE')
        missing = RESULT['examine'](P, {**files.values,'cycle':None}, lambda token:f.ok(token,'GET','/v1/self'))
        check(not missing['all_tokens_present'] and not missing['all_expected_memberships'], 'PROBE_MISSING_REFUSED')
        # Bad cryptographic signature is presented to real Kanidm and refused.
        bad = C.Portal(api, lambda *_: (_ for _ in ()).throw(RuntimeError('INVALID_DELIVERY')))
        first = bad.act('begin', {'identity':'portal-identity','access':None})
        try:
            bad.act('assert', {'transaction':first['transaction'],'assertion':keys['portal-identity'].assertion(first['challenge'], tamper=True)})
        except Exception:
            pass
        else:
            raise RuntimeError('INVALID_SIGNATURE_ACCEPTED')
        # Cancellation after first valid assertion revokes only that new session.
        cancelled = C.Portal(api, None)
        first = cancelled.act('begin', {'identity':'portal-identity','access':'portal-access'})
        nonce = first['transaction']
        cancelled.act('assert', {'transaction':nonce,'assertion':keys['portal-identity'].assertion(first['challenge'])})
        token = cancelled.transactions[nonce]['tokens'][0]
        check(cancelled.act('cancel', {'transaction':nonce}) == {'status':'CANCELLED'}, 'CANCEL_ACK')
        check(f.request(token,'GET','/v1/self')[0] == 401, 'CANCEL_REVOKED')
        check(f.request(identity_admin,'GET','/v1/self')[0] == 200 and f.request(access_admin,'GET','/v1/self')[0] == 200, 'UNRELATED_SESSIONS_PRESERVED')
        for item in (portal,same,bad,cancelled):
            check(item.cleanup(), 'FINAL_CLEANUP')
        return {'schema_version':1,'provider':'Kanidm 1.11.2','real_p256_passkey_registration':True,
                'real_p256_passkey_authentication':True,'invalid_signature_provider_refused':True,
                'separate_accounts':True,'same_account':True,'v2_cache_compatibility':True,
                'real_v2_worker_provision_and_idempotence':True,'commit_replay_refused':True,
                'dedicated_sessions_revoked':True,'cancel_revoked':True,'unrelated_sessions_preserved':True,
                'browser_responses_contain_only_challenge_status':True,'sensitive_memory_released':True,
                'read_only_result_probe_real_provider':True,'read_only_result_probe_missing_detected':True,
                'systemd_delivery_tested':False,'actual_proton_pass_browser_tested':False}


if __name__ == '__main__':
    print(json.dumps(qualify(), sort_keys=True, separators=(',',':')))
