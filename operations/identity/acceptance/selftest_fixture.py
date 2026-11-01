#!/usr/bin/env python3
"""Check the invented protocol fixtures without launching or reading a candidate."""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from urllib.parse import urlencode

from fixture import (ALICE, BOB, CLIENT_SECRET, HERE, ISSUER, Cryptography, Native,
                     Postgres, b64, command, parse_form, pkce, token, unique_pairs)

OPTIONS = None


class LoopbackTLS(http.client.HTTPConnection):
    def __init__(self, port, ca):
        super().__init__("127.0.0.1", port, timeout=5)
        self.context = ssl.create_default_context(cafile=ca)

    def connect(self):
        self.sock = self.context.wrap_socket(socket.create_connection(("127.0.0.1", self.port), timeout=5),
                                             server_hostname="log.mrj.am")


def decode_segment(segment):
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def der_integer(value):
    encoded = value.lstrip(b"\x00") or b"\x00"
    if encoded[0] & 0x80:
        encoded = b"\x00" + encoded
    return bytes((2, len(encoded))) + encoded


class FixtureSelfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="mrjam-id-selftest-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.root = Path(cls.workspace.name)
        cls.crypto = Cryptography(cls.root / "crypto", OPTIONS.openssl)
        cls.pg = Postgres(cls.root / "postgres", OPTIONS.postgres_bin)
        cls.addClassCleanup(cls.pg.close)

    def setUp(self):
        self.native = Native(self.crypto)
        self.addCleanup(self.native.close)

    def request(self, method, path, form=None, *, basic=False, ca=None):
        conn = LoopbackTLS(self.native.port, ca or self.crypto.ca)
        self.addCleanup(conn.close)
        headers = {"Host": "log.mrj.am", "Connection": "close"}
        if basic:
            headers["Authorization"] = "Basic " + base64.b64encode(("mrjam-vision:" + CLIENT_SECRET).encode()).decode()
        payload = None if form is None else urlencode(form).encode()
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read(), object_pairs_hook=unique_pairs)

    def authorization(self):
        verifier, nonce = token(), token()
        url = "https://log.mrj.am/ui/oauth2?" + urlencode({
            "client_id": "mrjam-vision", "code_challenge_method": "S256", "code_challenge": pkce(verifier),
            "nonce": nonce, "redirect_uri": "https://vision.mrj.am/auth/retour"})
        code = self.native.issue_code(url)
        return {"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                "redirect_uri": "https://vision.mrj.am/auth/retour"}, nonce

    def test_01_es256_fixture_signature_is_independently_verified(self):
        now = int(time.time())
        jwt = self.crypto.jwt({"iss": ISSUER, "sub": ALICE, "iat": now, "exp": now + 300})
        header, claims, signature = jwt.split(".")
        raw = decode_segment(signature)
        self.assertEqual(len(raw), 64)
        sequence = der_integer(raw[:32]) + der_integer(raw[32:])
        der = bytes((0x30, len(sequence))) + sequence
        public = self.root / "verify-public.pem"
        public.write_bytes(command([OPTIONS.openssl, "pkey", "-in", str(self.crypto.key), "-pubout"]))
        signature_file = self.root / "verify-signature.der"
        signature_file.write_bytes(der)
        message = (header + "." + claims).encode()
        answer = command([OPTIONS.openssl, "dgst", "-sha256", "-verify", str(public), "-signature", str(signature_file)], data=message)
        self.assertEqual(answer.strip(), b"Verified OK")
        with self.assertRaises(subprocess.CalledProcessError):
            command([OPTIONS.openssl, "dgst", "-sha256", "-verify", str(public), "-signature", str(signature_file)], data=message + b"x")
        self.assertEqual(json.loads(decode_segment(header))["alg"], "ES256")

    def test_02_tls_hostname_trust_discovery_and_public_jwks(self):
        status, discovery = self.request("GET", "/oauth2/openid/mrjam-vision/.well-known/openid-configuration")
        self.assertEqual(status, 200)
        self.assertEqual(discovery["issuer"], ISSUER)
        status, jwks = self.request("GET", "/oauth2/openid/mrjam-vision/public_key.jwk")
        self.assertEqual(status, 200)
        self.assertEqual(jwks, {"keys": [self.crypto.jwk]})
        self.assertEqual(self.native.seen_sni, ["log.mrj.am", "log.mrj.am"])
        other = Cryptography(self.root / "other-crypto", OPTIONS.openssl)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", "/oauth2/openid/mrjam-vision/public_key.jwk", ca=other.ca)

    def test_03_pkce_code_binding_and_introspection_authentication_profile(self):
        form, nonce = self.authorization()
        self.assertEqual(self.request("POST", "/oauth2/token", form)[0], 401)
        self.assertEqual(self.request("POST", "/oauth2/token", dict(form, code_verifier=token()), basic=True)[0], 400)
        self.assertEqual(self.request("POST", "/oauth2/token", form, basic=True)[0], 400)
        form, nonce = self.authorization()
        status, tokens = self.request("POST", "/oauth2/token", form, basic=True)
        self.assertEqual(status, 200)
        claims = json.loads(decode_segment(tokens["id_token"].split(".")[1]))
        self.assertEqual(claims["nonce"], nonce)
        self.assertEqual(claims["at_hash"], b64(hashlib.sha256(tokens["access_token"].encode()).digest()[:16]))
        self.assertEqual(self.request("POST", "/oauth2/token", form, basic=True)[0], 400)
        status, introspection = self.request("POST", "/oauth2/token/introspect", {"token": tokens["access_token"]})
        self.assertEqual(status, 200)
        self.assertTrue(introspection["active"])
        self.assertEqual(introspection["sub"], ALICE)
        self.assertEqual(self.request("POST", "/oauth2/token/introspect", {"token": tokens["access_token"]}, basic=True)[0], 400)

    def test_04_refresh_outage_recovery_and_revocation_have_distinct_effects(self):
        form, _nonce = self.authorization()
        status, tokens = self.request("POST", "/oauth2/token", form, basic=True)
        self.assertEqual(status, 200)
        refresh = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
        self.native.mode = "refresh_outage"
        self.assertEqual(self.request("POST", "/oauth2/token", refresh, basic=True)[0], 503)
        self.native.mode = None
        status, newer = self.request("POST", "/oauth2/token", refresh, basic=True)
        self.assertEqual(status, 200)
        self.assertNotEqual(newer["refresh_token"], tokens["refresh_token"])
        self.assertEqual(self.request("POST", "/oauth2/token", refresh, basic=True), (400, {"error": "invalid_grant"}))
        self.native.expire_access()
        self.assertFalse(self.request("POST", "/oauth2/token/introspect", {"token": newer["access_token"]})[1]["active"])
        self.assertEqual(self.request("POST", "/oauth2/token/revoke", {"token": newer["refresh_token"]})[0], 200)
        self.assertEqual(self.request("POST", "/oauth2/token", dict(refresh, refresh_token=newer["refresh_token"]), basic=True),
                         (400, {"error": "invalid_grant"}))

    def test_05_sql_function_maps_only_issuer_and_subject_with_restricted_role(self):
        query = "SELECT vision_gestion.identifier('" + ISSUER + "','" + ALICE + "')::text AS compte;"
        arguments = [str(OPTIONS.postgres_bin / "psql"), "-X", "-w", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-h",
                     str(self.pg.socket), "-p", str(self.pg.port), "-U", "vision_identite", "-d", "postgres"]
        document = json.loads(command(arguments, data=query.encode()))
        self.assertEqual(document, {"actif": True, "utilisateur": "synthetic_alice", "administrateur": True})
        foreign = query.replace(ISSUER, "https://issuer.invalid/")
        self.assertFalse(json.loads(command(arguments, data=foreign.encode()))["actif"])
        for forbidden in (b"SELECT * FROM public.synthetic_principals;", b"CREATE TABLE public.unexpected(id integer);"):
            with self.assertRaises(subprocess.CalledProcessError):
                command(arguments, data=forbidden)
        self.assertEqual(self.pg.sql("SHOW listen_addresses;"), "")

    def test_06_duplicate_json_form_and_mutations_are_real(self):
        with self.assertRaises(ValueError):
            parse_form(b"code=first&code=second")
        with self.assertRaises(ValueError):
            json.loads(b'{"sub":"first","sub":"second"}', object_pairs_hook=unique_pairs)
        form, _nonce = self.authorization()
        entry = self.native.codes[form["code"]]
        document = self.native.tokens(entry, "wrong_subject")
        self.assertEqual(json.loads(decode_segment(document["id_token"].split(".")[1]))["sub"], BOB)
        duplicate = self.native.tokens(entry, "duplicate_claim")["id_token"]
        with self.assertRaises(ValueError):
            json.loads(decode_segment(duplicate.split(".")[1]), object_pairs_hook=unique_pairs)


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--openssl", required=True)
    OPTIONS = parser.parse_args()
    OPTIONS.postgres_bin = OPTIONS.postgres_bin.resolve(strict=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixtureSelfTests))
    return 0 if result.wasSuccessful() and result.testsRun == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
