"""Invented local PostgreSQL, SQLite and TLS OIDC data for wire acceptance.

No production address, state, browser profile or credential is accepted here.
Run the candidate only in an appropriately isolated qualification environment.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

HERE = Path(__file__).resolve().parent
ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"
UNKNOWN = "33333333-3333-4333-8333-333333333333"
ISSUER = "https://log.mrj.am/oauth2/openid/mrjam-vision"
HOSTS = ("vision.mrj.am", "audition.mrj.am")
CLIENT_SECRET = "SYNTHETIC-ONLY-CLIENT-SECRET-DO-NOT-DEPLOY"
ENVIRONMENT = {"PATH": "/run/current-system/sw/bin", "LANG": "C", "LC_ALL": "C"}


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def token() -> str:
    return b64(secrets.token_bytes(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def pkce(value: str) -> str:
    return b64(hashlib.sha256(value.encode()).digest())


def canonical_json(document) -> bytes:
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATED_FIXTURE_FIELD")
        result[key] = value
    return result


def parse_form(data: bytes) -> dict[str, str]:
    decoded = parse_qs(data.decode("utf-8", "strict"), keep_blank_values=True, strict_parsing=True)
    if any(len(values) != 1 for values in decoded.values()):
        raise ValueError("DUPLICATED_FIXTURE_FIELD")
    return {key: values[0] for key, values in decoded.items()}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def command(arguments, *, data=None, timeout=30):
    return subprocess.run(arguments, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=ENVIRONMENT,
                          check=True, timeout=timeout).stdout


def raw_es256(signature: bytes) -> bytes:
    """Decode only the short DER ECDSA encoding produced by our OpenSSL fixture."""
    if len(signature) < 8 or signature[0] != 0x30 or signature[1] != len(signature) - 2:
        raise ValueError("INVALID_FIXTURE_SIGNATURE")
    values = []
    offset = 2
    for _ in range(2):
        if signature[offset] != 2:
            raise ValueError("INVALID_FIXTURE_SIGNATURE")
        length = signature[offset + 1]
        integer = signature[offset + 2:offset + 2 + length]
        if not 1 <= length <= 33 or len(integer) != length or integer[0] & 0x80:
            raise ValueError("INVALID_FIXTURE_SIGNATURE")
        value = int.from_bytes(integer, "big")
        values.append(value.to_bytes(32, "big"))
        offset += length + 2
    if offset != len(signature):
        raise ValueError("INVALID_FIXTURE_SIGNATURE")
    return b"".join(values)


class Cryptography:
    def __init__(self, folder: Path, openssl: str):
        self.folder = folder
        self.openssl = openssl
        folder.mkdir(mode=0o700)
        self.ca = folder / "ca.pem"
        self.key = folder / "oidc-key.pem"
        self.certificate = folder / "native.pem"
        self.tls_key = folder / "native-key.pem"
        command([openssl, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(self.key)])
        command([openssl, "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "2",
                 "-subj", "/CN=MRJAM-INDEPENDENT-SYNTHETIC-CA", "-addext", "basicConstraints=critical,CA:TRUE",
                 "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", str(folder / "ca-key.pem"),
                 "-out", str(self.ca)])
        command([openssl, "req", "-newkey", "rsa:2048", "-noenc", "-subj", "/CN=log.mrj.am",
                 "-keyout", str(self.tls_key), "-out", str(folder / "native.csr")])
        extensions = folder / "extensions.cnf"
        extensions.write_text("subjectAltName=DNS:log.mrj.am\nbasicConstraints=critical,CA:FALSE\n"
                              "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
        command([openssl, "x509", "-req", "-in", str(folder / "native.csr"), "-CA", str(self.ca),
                 "-CAkey", str(folder / "ca-key.pem"), "-CAcreateserial", "-days", "2",
                 "-extfile", str(extensions), "-out", str(self.certificate)])
        public_der = command([openssl, "pkey", "-in", str(self.key), "-pubout", "-outform", "DER"])
        point = public_der[-65:]
        if len(point) != 65 or point[0] != 4:
            raise ValueError("INVALID_FIXTURE_PUBLIC_KEY")
        self.jwk = {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
                    "kid": "SYNTHETIC-ES256-KEY", "x": b64(point[1:33]), "y": b64(point[33:])}

    def jwt(self, claims, mutation=None):
        header = {"alg": "ES256", "kid": self.jwk["kid"], "typ": "JWT"}
        payload = canonical_json(claims)
        if mutation == "injected_jku":
            header["jku"] = "https://unrequested.invalid/key"
        elif mutation == "injected_jwk":
            header["jwk"] = self.jwk
        elif mutation == "wrong_alg":
            header["alg"] = "HS256"
        elif mutation == "duplicate_claim":
            payload = payload[:-1] + b',"sub":"' + UNKNOWN.encode() + b'"}'
        elif mutation == "duplicate_header":
            encoded_header = b64(canonical_json(header)[:-1] + b',"alg":"none"}')
        if mutation != "duplicate_header":
            encoded_header = b64(canonical_json(header))
        signing_input = encoded_header + "." + b64(payload)
        signature = raw_es256(command([self.openssl, "dgst", "-sha256", "-sign", str(self.key)],
                                      data=signing_input.encode()))
        if mutation == "wrong_signature":
            signature = bytes([signature[0] ^ 1]) + signature[1:]
        return signing_input + "." + b64(signature)


class Postgres:
    """A new cluster, private Unix socket and no TCP listener; never a passed DSN."""
    def __init__(self, folder: Path, binaries: Path):
        if os.geteuid() == 0:
            raise ValueError("RUN_SYNTHETIC_HARNESS_AS_UNPRIVILEGED_USER")
        self.folder = folder
        self.binaries = binaries
        folder.mkdir(mode=0o700)
        self.socket = folder / "socket"
        self.socket.mkdir(mode=0o700)
        self.data = folder / "data"
        self.port = free_port()
        command([str(binaries / "initdb"), "-D", str(self.data), "-U", "postgres", "-A", "trust",
                 "--no-locale", "--encoding=UTF8"], timeout=60)
        self.started = False
        command([str(binaries / "pg_ctl"), "-D", str(self.data), "-l", str(folder / "synthetic-postgres.log"),
                 "-o", f"-k {self.socket} -p {self.port} -c listen_addresses='' -c fsync=off -c max_connections=30",
                 "-w", "start"], timeout=60)
        self.started = True
        try:
            self.sql((HERE / "principals.sql").read_text())
        except BaseException:
            self.close()
            raise

    def sql(self, source: str):
        return command([str(self.binaries / "psql"), "-X", "-w", "-v", "ON_ERROR_STOP=1", "-A", "-t",
                        "-h", str(self.socket), "-p", str(self.port), "-U", "postgres", "-d", "postgres"],
                       data=source.encode(), timeout=30).decode().strip()

    def close(self):
        if self.started:
            command([str(self.binaries / "pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"], timeout=60)
            self.started = False


class Native:
    """TLS protocol fixture, not an implementation of Kanidm authentication."""
    def __init__(self, crypto: Cryptography):
        self.crypto = crypto
        self.lock = threading.RLock()
        self.codes = {}
        self.access = {}
        self.refresh = {}
        self.sensitive_values = {CLIENT_SECRET}
        self.seen_sni = []
        self.requests = []
        self.mode = None
        self.refresh_mutation = None
        self.jwks_mode = None
        self.exchange_count = 0
        native = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.respond("GET")

            def do_POST(self):
                self.respond("POST")

            def respond(self, method):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 65536:
                        raise ValueError("BODY_LIMIT")
                    body = self.rfile.read(size)
                    with native.lock:
                        status, document, headers = native.dispatch(method, self.path, self.headers, body)
                    payload = document if isinstance(document, bytes) else canonical_json(document)
                except Exception:
                    status, payload, headers = 500, b'{"error":"fixture_error"}', {}
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(crypto.certificate, crypto.tls_key)
        context.set_servername_callback(lambda _socket, server_name, _ctx: self.seen_sni.append(server_name))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def issue_code(self, authorization, subject=ALICE, mutation=None, auth_time=None):
        values = parse_form(urlsplit(authorization).query.encode())
        if values.get("client_id") != "mrjam-vision" or values.get("code_challenge_method") != "S256":
            raise ValueError("INVALID_AUTHORIZATION_FIXTURE")
        code = "SYNTHETIC-CODE-" + token()
        entry = {"subject": subject, "nonce": values["nonce"], "challenge": values["code_challenge"],
                 "redirect": values["redirect_uri"], "mutation": mutation,
                 "auth_time": int(time.time()) if auth_time is None else auth_time}
        with self.lock:
            self.codes[code] = entry
            self.sensitive_values.add(code)
        return code

    def tokens(self, entry, mutation=None):
        now = int(time.time())
        access, refresh = "SYNTHETIC-ACCESS-" + token(), "SYNTHETIC-REFRESH-" + token()
        claims = {"iss": ISSUER, "sub": entry["subject"], "aud": "mrjam-vision", "nonce": entry["nonce"],
                  "exp": now + 300, "iat": now, "auth_time": entry["auth_time"],
                  "at_hash": b64(hashlib.sha256(access.encode()).digest()[:16])}
        if mutation == "wrong_issuer": claims["iss"] = "https://issuer.invalid/"
        if mutation == "wrong_audience": claims["aud"] = "another-client"
        if mutation == "wrong_azp": claims.update(aud=["mrjam-vision", "another-client"], azp="another-client")
        if mutation == "wrong_nonce": claims["nonce"] = token()
        if mutation == "expired": claims.update(exp=now - 60, iat=now - 3600, auth_time=now - 3600)
        if mutation == "future_iat": claims.update(iat=now + 120, exp=now + 500)
        if mutation == "future_nbf": claims["nbf"] = now + 120
        if mutation == "wrong_at_hash": claims["at_hash"] = b64(bytes(16))
        if mutation == "wrong_subject": claims["sub"] = BOB
        if mutation == "email_only": claims.update(sub=UNKNOWN, email="alice@synthetic.invalid")
        if mutation == "future_auth_time": claims["auth_time"] = now + 120
        if mutation == "fake_amr": claims["amr"] = ["mfa", "otp"]
        jwt = self.crypto.jwt(claims, mutation)
        self.access[access] = {"entry": dict(entry), "active": True, "exp": now + 300}
        self.refresh[refresh] = dict(entry)
        self.sensitive_values.update((access, refresh, jwt))
        return {"access_token": access, "refresh_token": refresh, "id_token": jwt,
                "token_type": "Bearer", "expires_in": 300}

    def dispatch(self, method, path, headers, body):
        self.requests.append({"method": method, "path": path, "authorization_present": "Authorization" in headers})
        if headers.get("Host") not in ("log.mrj.am", "log.mrj.am:443"):
            return 400, {"error": "host_required"}, {}
        if self.mode == "redirect":
            return 302, {}, {"Location": "https://unrequested.invalid/"}
        if method == "GET" and path == "/oauth2/openid/mrjam-vision/.well-known/openid-configuration":
            return 200, {"issuer": ISSUER, "authorization_endpoint": "https://log.mrj.am/ui/oauth2",
                         "token_endpoint": "https://log.mrj.am/oauth2/token", "jwks_uri": ISSUER + "/public_key.jwk",
                         "response_types_supported": ["code"], "id_token_signing_alg_values_supported": ["ES256"],
                         "code_challenge_methods_supported": ["S256"],
                         "token_endpoint_auth_methods_supported": ["client_secret_basic"]}, {}
        if method == "GET" and path == "/oauth2/openid/mrjam-vision/public_key.jwk":
            keys = [self.crypto.jwk]
            if self.jwks_mode == "duplicate_kid": keys = keys * 2
            if self.jwks_mode == "private_material": keys = [dict(self.crypto.jwk, d=token())]
            return 200, {"keys": keys}, {}
        if method != "POST":
            return 404, {}, {}
        form = parse_form(body)
        if path == "/oauth2/token":
            expected = "Basic " + base64.b64encode(("mrjam-vision:" + CLIENT_SECRET).encode()).decode()
            if headers.get("Authorization") != expected:
                return 401, {"error": "invalid_client"}, {}
            if form.get("grant_type") == "authorization_code":
                self.exchange_count += 1
                entry = self.codes.pop(form.get("code"), None)
                if self.mode == "token_outage":
                    return 503, {"error": "temporarily_unavailable"}, {}
                if not entry or entry["challenge"] != pkce(form.get("code_verifier", "")) or form.get("redirect_uri") != entry["redirect"]:
                    return 400, {"error": "invalid_grant"}, {}
                return 200, self.tokens(entry, entry["mutation"]), {}
            if form.get("grant_type") == "refresh_token":
                if self.mode == "refresh_outage":
                    return 503, {"error": "temporarily_unavailable"}, {}
                entry = self.refresh.get(form.get("refresh_token"))
                if self.mode == "refresh_revoked" or not entry:
                    return 400, {"error": "invalid_grant"}, {}
                self.refresh.pop(form["refresh_token"])
                return 200, self.tokens(entry, self.refresh_mutation), {}
            return 400, {"error": "unsupported_grant_type"}, {}
        if path == "/oauth2/token/introspect":
            if "Authorization" in headers:
                return 400, {"error": "unexpected_authentication"}, {}
            if self.mode == "introspection_outage":
                return 503, {"error": "temporarily_unavailable"}, {}
            if self.mode == "introspection_truncated":
                return 200, b'{"active":', {}
            record = self.access.get(form.get("token"))
            if not record:
                return 200, {"active": False}, {}
            return 200, {"active": record["active"], "exp": record["exp"],
                         "sub": record["entry"]["subject"], "client_id": "mrjam-vision"}, {}
        if path == "/oauth2/token/revoke":
            if "Authorization" in headers:
                return 400, {"error": "unexpected_authentication"}, {}
            if self.mode == "revoke_outage":
                return 503, {"error": "temporarily_unavailable"}, {}
            self.refresh.pop(form.get("token"), None)
            return 200, {}, {}
        return 404, {}, {}

    def expire_access(self):
        with self.lock:
            for entry in self.access.values():
                entry["active"] = False
                entry["exp"] = int(time.time()) - 1

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@dataclass
class Response:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def header(self, name):
        matches = [value for key, value in self.headers if key.lower() == name.lower()]
        if len(matches) != 1:
            raise AssertionError("REQUIRED_UNIQUE_RESPONSE_HEADER_" + name.upper())
        return matches[0]

    def values(self, name):
        return [value for key, value in self.headers if key.lower() == name.lower()]

    def document(self):
        return json.loads(self.body, object_pairs_hook=unique_pairs)


class Broker:
    def __init__(self, binary: Path, folder: Path, pg: Postgres, native: Native, crypto: Cryptography,
                 *, create_schema=True, configuration_changes=None):
        self.folder = folder
        folder.mkdir(mode=0o700)
        self.database = folder / "sessions.sqlite"
        if create_schema:
            with sqlite3.connect(self.database) as db:
                db.executescript((HERE / "legacy-state.sql").read_text())
                db.executemany("INSERT INTO log_principaux VALUES(?,?,?,?,?)", [
                    (ALICE, "alice@synthetic.invalid", 604800, "mfa", int(time.time()) - 10),
                    (BOB, "bob@synthetic.invalid", 604800, "any", int(time.time()) - 10)])
                self.initial_schema = db.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                self.initial_principals = db.execute("SELECT * FROM log_principaux ORDER BY subject").fetchall()
            self.database.chmod(0o600)
        secret = folder / "client-secret"
        secret.write_text(CLIENT_SECRET)
        secret.chmod(0o600)
        self.port = free_port()
        self.config = {"schema_version": 1, "listen": f"127.0.0.1:{self.port}",
                       "state_database": str(self.database), "kanidm_endpoint": f"127.0.0.1:{native.port}",
                       "kanidm_ca_file": str(crypto.ca),
                       "clients": [{"host": host, "client_id": "mrjam-vision", "secret_file": str(secret)} for host in HOSTS],
                       "principal_database": {"host": str(pg.socket), "port": pg.port, "database": "postgres", "user": "vision_identite"}}
        if configuration_changes:
            self.config.update(configuration_changes)
        config_file = folder / "config.json"
        config_file.write_bytes(canonical_json(self.config))
        config_file.chmod(0o600)
        self.output_path = folder / "candidate-output.log"
        self.output = self.output_path.open("xb")
        self.process = subprocess.Popen([str(binary), "serve", "--config", str(config_file)],
                                        stdin=subprocess.DEVNULL, stdout=self.output, stderr=subprocess.STDOUT,
                                        env=ENVIRONMENT, cwd=folder)

    def wait(self, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return True
            except OSError:
                time.sleep(0.05)
        return False

    def request(self, path, *, host=HOSTS[0], method="GET", cookie=None, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        pairs = [("Host", "mrj-auth.internal"), ("X-Forwarded-Host", host),
                 ("X-Forwarded-Proto", "https"), ("X-Original-Method", method)]
        if cookie:
            pairs.append(("Cookie", cookie))
        if headers:
            overrides = {key.lower() for key, _value in headers}
            pairs = [(key, value) for key, value in pairs if key.lower() not in overrides] + headers
        payload = body if isinstance(body, bytes) else b"" if body is None else canonical_json(body)
        if body is not None and not any(key.lower() == "content-type" for key, _ in pairs):
            pairs.append(("Content-Type", "application/json"))
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for key, value in pairs:
            connection.putheader(key, value)
        connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders(payload)
        try:
            response = connection.getresponse()
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise AssertionError("RESPONSE_EXCEEDS_FIXTURE_LIMIT")
            return Response(response.status, response.getheaders(), data)
        finally:
            connection.close()

    def sql(self, query, parameters=()):
        with sqlite3.connect(self.database, timeout=5) as db:
            return db.execute(query, parameters).fetchall()

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
                raise AssertionError("CANDIDATE_DID_NOT_DRAIN")
        self.output.close()

    def diagnostics(self):
        if not self.output.closed:
            self.output.flush()
        return self.output_path.read_bytes()


def session_cookie(response: Response):
    cookies = response.values("Set-Cookie")
    matches = [cookie for cookie in cookies if cookie.startswith("__Host-mrj_session=")]
    if len(matches) != 1:
        raise AssertionError("REQUIRED_SESSION_COOKIE")
    return matches[0].split(";", 1)[0]
