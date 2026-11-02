#!/usr/bin/env python3
"""Real Kanidm 1.11.2, invented identities, isolated loopback TLS and broker.

Run only through the accompanying bwrap launcher. No production paths or URLs.
The result contains checks and hashes, never credentials or native diagnostics.
"""
import argparse
import base64
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, "/acceptance")
import fixture
from fixture import Cryptography, Postgres, Broker, b64, canonical_json, pkce, token, session_cookie

ENVIRONMENT = {"PATH": "/bin", "HOME": "/tmp", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
ISSUER = "https://log.mrj.am/oauth2/openid/mrjam-vision"
STAGE = "initialization"
CHECKS = []
OBSERVATIONS = {}


def require(condition, code):
    if not condition:
        raise AssertionError(code)


class TLS(http.client.HTTPConnection):
    def __init__(self, port, ca):
        super().__init__("127.0.0.1", port, timeout=15)
        self.context = ssl.create_default_context(cafile=ca)

    def connect(self):
        self.sock = self.context.wrap_socket(socket.create_connection(("127.0.0.1", self.port), timeout=15),
                                             server_hostname="log.mrj.am")


class Native:
    def __init__(self, root, package, crypto):
        self.root, self.package, self.crypto = root, package, crypto
        root.mkdir(mode=0o700)
        self.port = fixture.free_port()
        self.config = root / "server.toml"
        self.config.write_text('\n'.join([
            'version = "2"', 'domain = "log.mrj.am"', 'origin = "https://log.mrj.am"',
            'bindaddress = "127.0.0.1:' + str(self.port) + '"',
            'db_path = ' + json.dumps(str(root / "kanidm.db")),
            'tls_chain = ' + json.dumps(str(crypto.certificate)), 'tls_key = ' + json.dumps(str(crypto.tls_key)),
            'adminbindpath = ' + json.dumps(str(root / "admin.sock")), 'log_level = "info"',
            '[online_backup]', 'enabled = false', 'path = ' + json.dumps(str(root / "backups")),
            'schedule = "00 22 * * *"', 'versions = 1', 'compression = "gzip"']) + '\n')
        self.log_path = root / "native-synthetic.log"
        self.process = None
        self.output = None
        self.start()

    def start(self):
        self.output = self.log_path.open("ab")
        self.process = subprocess.Popen([str(self.package / "bin/kanidmd"), "server", "-c", str(self.config)],
                                        env=ENVIRONMENT, cwd=self.root, stdin=subprocess.DEVNULL,
                                        stdout=self.output, stderr=subprocess.STDOUT)
        end = time.monotonic() + 90
        while time.monotonic() < end:
            require(self.process.poll() is None, "NATIVE_START_FAILED")
            try:
                if self.request("/status")[0] == 200:
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(.2)
        raise AssertionError("NATIVE_START_TIMEOUT")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=30)
        if self.output:
            self.output.close()

    def request(self, path, body=None, *, method=None, bearer=None, basic=None, cookie=None, form=False):
        connection = TLS(self.port, self.crypto.ca)
        headers = {"Host": "log.mrj.am", "Connection": "close", "Accept": "application/json"}
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        if basic:
            headers["Authorization"] = "Basic " + base64.b64encode(("mrjam-vision:" + basic).encode()).decode()
        if cookie:
            headers["Cookie"] = cookie
        payload = None
        if body is not None:
            payload = urlencode(body).encode() if form else canonical_json(body)
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        try:
            connection.request(method or ("POST" if body is not None else "GET"), path, payload, headers)
            response = connection.getresponse()
            data = response.read(1024 * 1024 + 1)
            require(len(data) <= 1024 * 1024, "NATIVE_RESPONSE_LIMIT")
            return response.status, dict(response.getheaders()), data
        finally:
            connection.close()

    def api(self, path, body=None, **kwargs):
        status, headers, data = self.request(path, body, **kwargs)
        require(status == 200, "NATIVE_API_HTTP_" + str(status))
        return json.loads(data) if data else None

    def recover(self, name):
        require(name in ("idm_admin", "synthetic_native_alice"), "FIXTURE_ACCOUNT_SCOPE")
        result = subprocess.run([str(self.package / "bin/kanidmd"), "-c", str(self.config), "scripting", "recover-account", name],
                                env=ENVIRONMENT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=60)
        require(result.returncode == 0, "FIXTURE_RECOVERY_FAILED")
        document = json.loads(result.stdout)
        require(document.get("status") == "ok" and isinstance(document.get("output"), str), "FIXTURE_RECOVERY_SHAPE")
        return document["output"]

    def login(self, name, password, privileged):
        jar = {}
        requests = [({"step": {"init2": {"username": name, "issue": "token", "privileged": privileged}}}, "choose"),
                    ({"step": {"begin": "password"}}, "continue"),
                    ({"step": {"cred": {"password": password}}}, "success")]
        for request, expected in requests:
            status, headers, data = self.request("/v1/auth", request, cookie="; ".join(k + "=" + v for k, v in jar.items()))
            require(status == 200, "NATIVE_AUTH_HTTP_" + str(status))
            for header, value in headers.items():
                if header.lower() == "set-cookie":
                    parsed = SimpleCookie()
                    parsed.load(value)
                    jar.update({key: item.value for key, item in parsed.items()})
            document = json.loads(data)
            require(expected in document.get("state", {}), "NATIVE_AUTH_STATE_" + expected)
        return document["state"]["success"]

    def authorize(self, query, bearer):
        status, headers, data = self.request("/oauth2/authorise?" + query, bearer=bearer)
        if status == 200:
            document = json.loads(data)
            require("ConsentRequested" in document, "NATIVE_CONSENT_SHAPE")
            consent = document["ConsentRequested"]["consent_token"]
            status, headers, data = self.request("/oauth2/authorise/permit?" + urlencode({"token": consent}), bearer=bearer)
        require(status == 302, "NATIVE_AUTHORIZE_HTTP_" + str(status))
        location = next((v for k, v in headers.items() if k.lower() == "location"), None)
        require(isinstance(location, str), "NATIVE_AUTHORIZE_LOCATION")
        return location


def verify_jwt(jwt, jwks, nonce, access, subject, openssl, root):
    segments = jwt.split(".")
    require(len(segments) == 3, "JWT_SHAPE")
    decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    header, claims = (json.loads(decode(value)) for value in segments[:2])
    require(header["alg"] == "ES256", "JWT_ALGORITHM")
    key = [entry for entry in jwks["keys"] if entry.get("kid") == header["kid"]]
    require(len(key) == 1 and key[0]["kty"] == "EC" and key[0]["crv"] == "P-256" and "d" not in key[0], "JWT_JWKS_PROFILE")
    point = b"\x04" + decode(key[0]["x"]) + decode(key[0]["y"])
    require(len(point) == 65, "JWT_PUBLIC_KEY_SIZE")
    # RFC5480 SubjectPublicKeyInfo for id-ecPublicKey with prime256v1.
    public_der = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200") + point
    public_file = root / "native-jwt-public.der"
    public_file.write_bytes(public_der)
    raw = decode(segments[2])
    require(len(raw) == 64, "JWT_SIGNATURE_SIZE")
    def integer(value):
        value = value.lstrip(b"\x00") or b"\x00"
        if value[0] & 128:
            value = b"\x00" + value
        return bytes((2, len(value))) + value
    sequence = integer(raw[:32]) + integer(raw[32:])
    signature = root / "native-jwt-signature.der"
    signature.write_bytes(bytes((48, len(sequence))) + sequence)
    result = subprocess.run([openssl, "dgst", "-sha256", "-verify", str(public_file), "-keyform", "DER", "-signature", str(signature)],
                            input=(segments[0] + "." + segments[1]).encode(), env=ENVIRONMENT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    require(result.returncode == 0, "JWT_SIGNATURE_INVALID")
    require(claims["iss"] == ISSUER and claims["aud"] == "mrjam-vision" and claims["sub"] == subject, "JWT_IDENTITY_BINDING")
    require(claims["nonce"] == nonce and claims["exp"] > int(time.time()), "JWT_TRANSACTION_TIME")
    if "at_hash" in claims:
        require(claims["at_hash"] == b64(hashlib.sha256(access.encode()).digest()[:16]), "JWT_ACCESS_BINDING")
    require(isinstance(claims.get("auth_time"), int), "JWT_AUTH_TIME_MISSING")


def qualify(options):
    global STAGE
    with tempfile.TemporaryDirectory(prefix="mrjam-native-") as directory:
        root = Path(directory)
        crypto = Cryptography(root / "crypto", options.openssl)
        native, pg, broker = None, None, None
        try:
            STAGE = "real-kanidm-bootstrap-tls"
            native = Native(root / "native", options.kanidm, crypto)
            CHECKS.append(STAGE)
            STAGE = "invented-oauth-client-and-person"
            admin = native.login("idm_admin", native.recover("idm_admin"), True)
            native.api("/v1/person", {"attrs": {"name": ["synthetic_native_alice"], "displayname": ["Synthetic Native Alice"],
                                                "mail": ["alice@synthetic.invalid"]}}, bearer=admin)
            subject = native.api("/v1/person/synthetic_native_alice", bearer=admin)["attrs"]["uuid"][0]
            native.api("/v1/oauth2/_basic", {"attrs": {"name": ["mrjam-vision"], "displayname": ["Synthetic MRJ acceptance"],
                                                      "oauth2_rs_origin_landing": ["https://vision.mrj.am/"],
                                                      "oauth2_strict_redirect_uri": ["true"]}}, bearer=admin)
            native.api("/v1/oauth2/mrjam-vision/_attr/oauth2_rs_origin",
                       ["https://vision.mrj.am/auth/retour", "https://audition.mrj.am/auth/retour"], bearer=admin)
            native.api("/v1/oauth2/mrjam-vision/_scopemap/idm_all_persons", ["openid", "profile", "email"], bearer=admin)
            secret = native.api("/v1/oauth2/mrjam-vision/_basic_secret", bearer=admin)
            user = native.login("synthetic_native_alice", native.recover("synthetic_native_alice"), False)
            CHECKS.append(STAGE)
            STAGE = "native-discovery-and-jwks"
            discovery = native.api("/oauth2/openid/mrjam-vision/.well-known/openid-configuration")
            require(discovery["issuer"] == ISSUER and "ES256" in discovery["id_token_signing_alg_values_supported"], "DISCOVERY_PROFILE")
            require("S256" in discovery["code_challenge_methods_supported"], "DISCOVERY_PKCE")
            require("client_secret_basic" in discovery["token_endpoint_auth_methods_supported"], "DISCOVERY_BASIC")
            jwks = native.api("/oauth2/openid/mrjam-vision/public_key.jwk")
            CHECKS.append(STAGE)
            STAGE = "native-authorization-token-signature-introspection"
            verifier, nonce, state = token(), token(), token()
            query = urlencode({"client_id": "mrjam-vision", "response_type": "code", "scope": "openid email profile",
                               "redirect_uri": "https://vision.mrj.am/auth/retour", "state": state, "nonce": nonce,
                               "code_challenge": pkce(verifier), "code_challenge_method": "S256"})
            redirect = native.authorize(query, user)
            returned = parse_qs(urlsplit(redirect).query)
            require(returned["state"] == [state], "NATIVE_STATE_RETURN")
            form = {"grant_type": "authorization_code", "code": returned["code"][0], "code_verifier": verifier,
                    "redirect_uri": "https://vision.mrj.am/auth/retour"}
            require(native.request("/oauth2/token", dict(form, code_verifier=token()), basic=secret, form=True)[0] == 400,
                    "NATIVE_INVALID_PKCE_ACCEPTED")
            require(native.request("/oauth2/token", form, form=True)[0] in (400, 401), "NATIVE_BASIC_MISSING_ACCEPTED")
            tokens = native.api("/oauth2/token", form, basic=secret, form=True)
            verify_jwt(tokens["id_token"], jwks, nonce, tokens["access_token"], subject, options.openssl, root)
            introspection = native.api("/oauth2/token/introspect", {"token": tokens["access_token"]}, form=True)
            require(introspection["active"] is True, "NATIVE_INTROSPECTION_INACTIVE")
            replay_status = native.request("/oauth2/token", form, basic=secret, form=True)[0]
            # v1.11.2's check_oauth2_token_exchange_authorization_code creates a
            # fresh session_id after JWE/PKCE validation without consuming code.
            # Preserve the limitation; the broker's transaction must refuse it.
            OBSERVATIONS["native_code_replay_http_status"] = replay_status
            OBSERVATIONS["native_code_replay_refused"] = replay_status in (400, 401)
            CHECKS.append(STAGE)
            STAGE = "native-refresh-signature-and-revocation"
            refreshed = native.api("/oauth2/token", {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}, basic=secret, form=True)
            verify_jwt(refreshed["id_token"], jwks, nonce, refreshed["access_token"], subject, options.openssl, root)
            native.api("/oauth2/token/revoke", {"token": refreshed["refresh_token"], "token_type_hint": "refresh_token"}, form=True)
            require(native.api("/oauth2/token/introspect", {"token": refreshed["access_token"]}, form=True)["active"] is False,
                    "NATIVE_REVOKED_STILL_ACTIVE")
            CHECKS.append(STAGE)
            STAGE = "broker-real-native-callback-and-host-audiences"
            pg = Postgres(root / "postgres", options.postgres_bin)
            pg.sql("UPDATE public.synthetic_principals SET subject='" + subject + "', username='synthetic_native_alice', administrator=false WHERE subject='" + fixture.ALICE + "';")
            fixture.CLIENT_SECRET = secret
            broker = Broker(options.binary, root / "broker", pg, native, crypto)
            require(broker.wait(), "BROKER_START_FAILED")
            cookies = {}
            for host in fixture.HOSTS:
                start = broker.request("/auth/connexion?retour=%2F", host=host)
                require(start.status == 302, "BROKER_LOGIN_START")
                redirect = native.authorize(urlsplit(start.header("Location")).query, user)
                callback = broker.request("/auth/retour?" + urlsplit(redirect).query, host=host,
                                          cookie=start.header("Set-Cookie").split(";", 1)[0])
                require(callback.status == 302, "BROKER_CALLBACK_HTTP_" + str(callback.status))
                replay = broker.request("/auth/retour?" + urlsplit(redirect).query, host=host,
                                        cookie=start.header("Set-Cookie").split(";", 1)[0])
                require(replay.status == 401, "BROKER_NATIVE_CALLBACK_REPLAY_ACCEPTED")
                cookies[host] = session_cookie(callback)
                verified = broker.request("/verify", host=host, cookie=cookies[host])
                require(verified.status == 204 and verified.header("X-Mrj-User") == "synthetic_native_alice", "BROKER_NATIVE_VERIFY")
                require(broker.request("/verify-gestion", host=host, cookie=cookies[host]).status == 403, "UNQUALIFIED_MFA_GRANTED")
            require(broker.request("/verify", host=fixture.HOSTS[1], cookie=cookies[fixture.HOSTS[0]]).status == 401, "CROSS_HOST_SESSION")
            CHECKS.append(STAGE)
            STAGE = "native-outage-and-restart-preserve-broker-session"
            native.stop()
            require(broker.request("/verify", cookie=cookies[fixture.HOSTS[0]]).status == 503, "NATIVE_OUTAGE_WRONG_STATUS")
            require(broker.sql("SELECT count(*) FROM log_sessions") == [(2,)], "OUTAGE_DESTROYED_SESSION")
            native.start()
            require(broker.request("/verify", cookie=cookies[fixture.HOSTS[0]]).status == 204, "NATIVE_RESTART_LOST_SESSION")
            CHECKS.append(STAGE)
            STAGE = "broker-local-and-real-native-logout"
            session = broker.request("/auth/session", cookie=cookies[fixture.HOSTS[0]]).document()
            logout = broker.request("/auth/logout", method="POST", cookie=cookies[fixture.HOSTS[0]],
                                    headers=[("Origin", "https://vision.mrj.am"), ("X-CSRF-Token", session["csrf"])])
            require(logout.status == 200, "NATIVE_LOGOUT_FAILED")
            require(broker.request("/verify", cookie=cookies[fixture.HOSTS[0]]).status == 401, "LOCAL_LOGOUT_FAILED")
            require(broker.request("/verify", host=fixture.HOSTS[1], cookie=cookies[fixture.HOSTS[1]]).status == 204, "UNRELATED_LOGOUT")
            broker.stop()
            require(secret.encode() not in broker.diagnostics() and subject.encode() not in broker.diagnostics(), "BROKER_DIAGNOSTIC_DISCLOSURE")
            CHECKS.append(STAGE)
        finally:
            if broker:
                broker.stop()
            if pg:
                pg.close()
            if native:
                native.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--kanidm", type=Path, required=True)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--openssl", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    require(not options.output.exists(), "NEW_RESULT_REQUIRED")
    receipt = {"schema_version": 1, "scope": "isolated-real-kanidm-invented-identity-wire-qualification",
               "kanidm": str(options.kanidm), "candidate_sha256": hashlib.sha256(options.binary.read_bytes()).hexdigest(),
               "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "production_access": False,
               "actual_production_sso_qualified": False, "human_mfa_qualified": False, "checks": CHECKS,
               "upstream_observations": OBSERVATIONS,
               "passed": False}
    try:
        qualify(options)
        receipt["passed"] = True
    except Exception as error:
        receipt["failed_stage"] = STAGE
        receipt["error_class"] = type(error).__name__
        receipt["failure_code"] = str(error) if isinstance(error, AssertionError) else "FIXTURE_OR_NATIVE_ERROR"
    with options.output.open("x") as target:
        json.dump(receipt, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps({key: receipt[key] for key in ("passed", "checks", "failed_stage", "error_class", "failure_code") if key in receipt}, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
