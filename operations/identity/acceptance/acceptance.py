#!/usr/bin/env python3
"""Independent wire tests; launch only in an isolated synthetic environment.

The CLI accepts executable paths, never a production DSN, state path or URL.
All native credentials, subjects, databases and keys are invented locally.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from fixture import (ALICE, BOB, CLIENT_SECRET, HERE, HOSTS, ISSUER, Broker,
                     Cryptography, Native, Postgres, digest, parse_form, pkce,
                     session_cookie, token)

OPTIONS = None


class NativeIdentityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="mrjam-id-acceptance-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.root = Path(cls.workspace.name)
        cls.crypto = Cryptography(cls.root / "crypto", OPTIONS.openssl)
        cls.pg = Postgres(cls.root / "postgres", OPTIONS.postgres_bin)
        cls.addClassCleanup(cls.pg.close)

    def setUp(self):
        self.native = Native(self.crypto)
        self.addCleanup(self.native.close)
        self.case_directory = Path(tempfile.mkdtemp(prefix="case-", dir=self.root))
        self.brokers = []
        self.secrets = set()
        self.responses = []
        self.pg.sql("UPDATE public.synthetic_principals SET active=true, "
                    "username=CASE WHEN subject='" + ALICE + "' THEN 'synthetic_alice' ELSE 'synthetic_bob' END, "
                    "administrator=(subject='" + ALICE + "');")

    def tearDown(self):
        failures = []
        for broker in self.brokers:
            try:
                broker.stop()
            except Exception as error:
                failures.append(type(error).__name__)
        self.assertEqual(failures, [], "CANDIDATE_DRAIN_FAILED")
        for broker in self.brokers:
            diagnostics = broker.output_path.read_bytes()
            for secret in self.secrets | self.native.sensitive_values | {ALICE, BOB}:
                self.assertNotIn(secret.encode(), diagnostics, "CANDIDATE_DIAGNOSTIC_DISCLOSURE")
        for response in self.responses:
            serialized = response.body + repr(response.headers).encode()
            for secret in self.native.sensitive_values | {ALICE, BOB}:
                self.assertNotIn(secret.encode(), serialized, "NATIVE_CREDENTIAL_RESPONSE_DISCLOSURE")
            if response.status >= 400:
                for secret in self.secrets | self.native.sensitive_values | {ALICE, BOB}:
                    self.assertNotIn(secret.encode(), serialized, "ERROR_RESPONSE_DISCLOSURE")

    def launch(self, **options):
        broker = Broker(OPTIONS.binary, self.case_directory / ("broker-" + str(len(self.brokers))),
                        self.pg, self.native, self.crypto, **options)
        self.brokers.append(broker)
        return broker

    def running(self, **options):
        broker = self.launch(**options)
        self.assertTrue(broker.wait(), "CANDIDATE_START_FAILED")
        return broker

    def request(self, broker, path, **kwargs):
        response = broker.request(path, **kwargs)
        self.responses.append(response)
        return response

    def begin(self, broker, host=HOSTS[0], *, retour="/", verification=None):
        parameters = {"retour": retour}
        if verification:
            parameters["verification"] = verification
        response = self.request(broker, "/auth/connexion?" + urlencode(parameters), host=host)
        self.assertEqual(response.status, 302, "LOGIN_START_STATUS")
        location = response.header("Location")
        parsed = urlsplit(location)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "log.mrj.am", "/ui/oauth2"))
        values = parse_form(parsed.query.encode())
        self.assertEqual(values["client_id"], "mrjam-vision")
        self.assertEqual(values["redirect_uri"], "https://" + host + "/auth/retour")
        self.assertEqual(values["response_type"], "code")
        self.assertEqual(values["scope"], "openid email profile")
        self.assertEqual(values["code_challenge_method"], "S256")
        for name in ("state", "nonce", "code_challenge"):
            self.assertRegex(values[name], r"^[A-Za-z0-9_-]{43}$")
        cookies = response.values("Set-Cookie")
        self.assertEqual(len(cookies), 1)
        cookie = cookies[0]
        self.assertTrue(cookie.startswith("__Host-mrj_oidc_" + values["state"] + "="))
        self.assertCookieFlags(cookie, maximum=600)
        binding = cookie.split(";", 1)[0].split("=", 1)[1]
        self.secrets.update((binding, values["state"], values["nonce"]))
        row = broker.sql("SELECT binding,host,client_id,verifier,nonce,retour FROM log_transactions WHERE state=?",
                         (digest(values["state"]),))
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0][:3], (digest(binding), host, "mrjam-vision"))
        self.assertEqual(pkce(row[0][3]), values["code_challenge"])
        self.assertEqual(row[0][4:], (values["nonce"], retour))
        self.assertNotIn(row[0][3], location)
        self.secrets.add(row[0][3])
        self.assertNotIn(CLIENT_SECRET, location)
        return {"location": location, "state": values["state"], "cookie": cookie.split(";", 1)[0], "host": host}

    def callback(self, broker, start, code, *, cookie=None, host=None):
        return self.request(broker, "/auth/retour?" + urlencode({"state": start["state"], "code": code}),
                            cookie=start["cookie"] if cookie is None else cookie,
                            host=start["host"] if host is None else host)

    def login(self, broker, host=HOSTS[0], subject=ALICE, *, mutation=None, auth_time=None):
        start = self.begin(broker, host)
        code = self.native.issue_code(start["location"], subject=subject, mutation=mutation, auth_time=auth_time)
        response = self.callback(broker, start, code)
        self.assertEqual(response.status, 302, "LOGIN_CALLBACK_STATUS")
        self.assertEqual(response.header("Location"), "/")
        cookie = session_cookie(response)
        self.secrets.add(cookie.split("=", 1)[1])
        full = next(item for item in response.values("Set-Cookie") if item.startswith("__Host-mrj_session="))
        self.assertCookieFlags(full, maximum=604800)
        self.assertTrue(any(item.startswith("__Host-mrj_oidc_" + start["state"] + "=") and "Max-Age=0" in item
                            for item in response.values("Set-Cookie")))
        self.assertEqual(broker.sql("SELECT count(*) FROM log_transactions WHERE state=?", (digest(start["state"]),)), [(0,)])
        return cookie

    def assertCookieFlags(self, cookie, maximum):
        values = [part.strip() for part in cookie.split(";")]
        for required in ("Path=/", "Secure", "HttpOnly", "SameSite=Lax", "Max-Age=" + str(maximum)):
            self.assertIn(required, values)
        self.assertFalse(any(part.lower().startswith("domain=") for part in values))

    def verify(self, broker, cookie, *, host=HOSTS[0], management=False, headers=None):
        return self.request(broker, "/verify-gestion" if management else "/verify", cookie=cookie,
                            host=host, headers=headers)

    def csrf(self, broker, cookie, host=HOSTS[0]):
        response = self.request(broker, "/auth/session", cookie=cookie, host=host)
        self.assertEqual(response.status, 200)
        document = response.document()
        self.assertRegex(document["csrf"], r"^[A-Za-z0-9_-]{43}$")
        self.secrets.add(document["csrf"])
        for secret in self.native.sensitive_values:
            self.assertNotIn(secret.encode(), response.body)
        for name in ("access_token", "refresh_token", "id_token", "nonce", "subject"):
            self.assertNotIn(name, document)
        return [("Origin", "https://" + host), ("X-CSRF-Token", document["csrf"])]

    def register(self, broker, host=HOSTS[0]):
        response = self.request(broker, "/oauth/register", method="POST", host=host,
                                body={"client_name": "Independent synthetic MCP", "redirect_uris": ["https://client.example.test/return"]})
        self.assertEqual(response.status, 201)
        doc = response.document()
        self.assertRegex(doc["client_id"], r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(doc["token_endpoint_auth_method"], "none")
        return doc["client_id"]

    def consent_request(self, broker, cookie, client, host=HOSTS[0], **changes):
        verifier = token()
        query = {"client_id": client, "redirect_uri": "https://client.example.test/return", "response_type": "code",
                 "code_challenge_method": "S256", "code_challenge": pkce(verifier), "state": "synthetic-client-state",
                 "scope": "audition:mcp" if host == HOSTS[1] else "vision:mcp", "resource": "https://" + host + "/mcp"}
        query.update(changes)
        response = self.request(broker, "/oauth/authorize?" + urlencode(query), host=host, cookie=cookie)
        self.assertEqual(response.status, 302)
        location = response.header("Location")
        self.assertRegex(location, r"^/#autorisation-mcp=[A-Za-z0-9_-]{43}$")
        return {"id": location.split("=", 1)[1], "verifier": verifier, "client": client, "host": host}

    def consent(self, broker, cookie, request, *, accepted=True, headers=None):
        if headers is None:
            headers = self.csrf(broker, cookie, request["host"])
        return self.request(broker, "/auth/oauth-consentement", method="POST", host=request["host"], cookie=cookie,
                            headers=headers, body={"id": request["id"], "decision": "autoriser" if accepted else "refuser"})

    def token_request(self, broker, form, host=HOSTS[0]):
        return self.request(broker, "/oauth/token", method="POST", host=host, body=urlencode(form).encode(),
                            headers=[("Content-Type", "application/x-www-form-urlencoded")])

    def issue_mcp(self, broker, cookie, client, host=HOSTS[0]):
        request = self.consent_request(broker, cookie, client, host)
        response = self.consent(broker, cookie, request)
        self.assertEqual(response.status, 200)
        redirect = response.document()["redirection"]
        values = parse_form(urlsplit(redirect).query.encode())
        self.assertEqual(values["state"], "synthetic-client-state")
        form = {"grant_type": "authorization_code", "client_id": client, "code": values["code"],
                "redirect_uri": "https://client.example.test/return", "code_verifier": request["verifier"],
                "resource": "https://" + host + "/mcp"}
        response = self.token_request(broker, form, host)
        self.assertEqual(response.status, 200)
        tokens = response.document()
        self.secrets.update((tokens["access_token"], tokens["refresh_token"], values["code"], request["verifier"]))
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertEqual(tokens["scope"], "audition:mcp" if host == HOSTS[1] else "vision:mcp")
        self.assertTrue(0 < tokens["expires_in"] <= 3600)
        return tokens, form

    def mcp_verify(self, broker, access, host=HOSTS[0]):
        return self.request(broker, "/verify-mcp", host=host, headers=[("Authorization", "Bearer " + access)])

    def test_01_existing_schema_retained_and_absent_schema_refused(self):
        broker = self.launch()
        self.assertTrue(broker.wait())
        self.assertEqual(broker.sql("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"), broker.initial_schema)
        self.assertEqual(broker.sql("SELECT * FROM log_principaux ORDER BY subject"), broker.initial_principals)
        missing = self.launch(create_schema=False)
        self.assertFalse(missing.wait(timeout=3), "ABSENT_STATE_MUST_NOT_BOOTSTRAP")
        self.assertFalse(missing.database.exists(), "MISSING_STATE_FILE_CREATED")

    def test_02_missing_credentials_and_spoofed_identity_headers_refused(self):
        broker = self.running()
        for host in HOSTS:
            for endpoint in ("/verify", "/verify-gestion", "/verify-mcp"):
                response = self.request(broker, endpoint, host=host,
                                        headers=[("X-Mrj-User", "synthetic_alice"), ("X-Mrj-Administrator", "true")])
                self.assertEqual(response.status, 401)
                self.assertEqual(response.values("X-Mrj-User"), [])

    def test_03_real_signed_login_host_isolation_and_safe_session(self):
        broker = self.running()
        cookie = self.login(broker)
        response = self.verify(broker, cookie)
        self.assertEqual(response.status, 204)
        self.assertEqual(response.header("X-Mrj-User"), "synthetic_alice")
        self.assertEqual(response.body, b"")
        self.assertFalse(response.values("Location") or response.values("Set-Cookie"))
        self.assertEqual(self.verify(broker, cookie, host=HOSTS[1]).status, 401)
        self.csrf(broker, cookie)
        self.assertTrue(self.native.seen_sni)
        self.assertTrue(all(name == "log.mrj.am" for name in self.native.seen_sni))

    def test_04_two_tabs_distinct_bindings_and_callback_replay(self):
        broker = self.running()
        first, second = self.begin(broker), self.begin(broker)
        self.assertNotEqual(first["state"], second["state"])
        combined = first["cookie"] + "; " + second["cookie"]
        for start in (second, first):
            code = self.native.issue_code(start["location"])
            self.assertEqual(self.callback(broker, start, code, cookie=combined).status, 302)
            self.assertEqual(self.callback(broker, start, code, cookie=combined).status, 401)
        self.assertEqual(self.native.exchange_count, 2)

    def test_05_wrong_browser_binding_or_host_cannot_consume_transaction(self):
        broker = self.running()
        start = self.begin(broker)
        code = self.native.issue_code(start["location"])
        wrong_cookie = start["cookie"].split("=", 1)[0] + "=" + token()
        self.assertEqual(self.callback(broker, start, code, cookie=wrong_cookie).status, 401)
        self.assertEqual(self.callback(broker, start, code, host=HOSTS[1]).status, 401)
        self.assertEqual(self.native.exchange_count, 0)
        self.assertEqual(self.callback(broker, start, code).status, 302)

    def test_06_invalid_signed_token_profiles_rejected(self):
        broker = self.running()
        mutations = ("wrong_issuer", "wrong_audience", "wrong_azp", "wrong_nonce", "expired", "future_iat",
                     "future_nbf", "future_auth_time", "wrong_at_hash", "wrong_signature", "wrong_alg",
                     "injected_jku", "injected_jwk", "duplicate_claim", "duplicate_header")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                start = self.begin(broker)
                code = self.native.issue_code(start["location"], mutation=mutation)
                response = self.callback(broker, start, code)
                self.assertEqual(response.status, 401, "INVALID_TOKEN_PROFILE_ACCEPTED")
                self.assertFalse(any(cookie.startswith("__Host-mrj_session=") for cookie in response.values("Set-Cookie")))
                self.assertEqual(broker.sql("SELECT count(*) FROM log_transactions WHERE state=?", (digest(start["state"]),)), [(0,)])
        self.assertEqual(broker.sql("SELECT count(*) FROM log_sessions"), [(0,)])

    def test_07_trusted_jwks_must_have_unique_kid_and_no_private_key(self):
        broker = self.running()
        for mutation in ("duplicate_kid", "private_material"):
            with self.subTest(mutation=mutation):
                self.native.jwks_mode = mutation
                start = self.begin(broker)
                response = self.callback(broker, start, self.native.issue_code(start["location"]))
                self.assertEqual(response.status, 401)
                self.assertFalse(any(cookie.startswith("__Host-mrj_session=") for cookie in response.values("Set-Cookie")))

    def test_08_callback_committed_before_upstream_failure_or_concurrent_retry(self):
        broker = self.running()
        start = self.begin(broker)
        code = self.native.issue_code(start["location"])
        self.native.mode = "token_outage"
        first = self.callback(broker, start, code)
        self.assertIn(first.status, (401, 503))
        self.native.mode = None
        self.assertEqual(self.callback(broker, start, code).status, 401)
        self.assertEqual(self.native.exchange_count, 1)
        self.assertEqual(broker.sql("SELECT count(*) FROM log_transactions WHERE state=?", (digest(start["state"]),)), [(0,)])
        start = self.begin(broker)
        code = self.native.issue_code(start["location"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _n: self.callback(broker, start, code), range(2)))
        self.assertEqual(sorted(response.status for response in responses), [302, 401])
        self.assertEqual(self.native.exchange_count, 2)

    def test_09_business_subject_mapping_checked_each_access(self):
        broker = self.running()
        start = self.begin(broker)
        response = self.callback(broker, start, self.native.issue_code(start["location"], mutation="email_only"))
        self.assertEqual(response.status, 403, "EMAIL_MUST_NOT_MAP_AN_UNKNOWN_SUBJECT")
        cookie = self.login(broker)
        self.pg.sql("UPDATE public.synthetic_principals SET active=false WHERE subject='" + ALICE + "';")
        self.assertEqual(self.verify(broker, cookie).status, 403)
        self.pg.sql("UPDATE public.synthetic_principals SET active=true, username='synthetic_reassigned' WHERE subject='" + ALICE + "';")
        self.assertEqual(self.verify(broker, cookie).status, 403)
        self.pg.sql("UPDATE public.synthetic_principals SET username='synthetic_alice' WHERE subject='" + ALICE + "';")
        self.assertEqual(self.verify(broker, cookie).status, 204)

    def test_10_unsafe_original_method_requires_same_origin_and_csrf(self):
        broker = self.running()
        cookie = self.login(broker)
        good = self.csrf(broker, cookie)
        for extras in ([], [("Origin", "https://unrequested.invalid")],
                       [("Origin", "https://" + HOSTS[0]), ("X-CSRF-Token", token())]):
            self.assertEqual(self.verify(broker, cookie, headers=[("X-Original-Method", "POST")] + extras).status, 403)
        self.assertEqual(self.verify(broker, cookie, headers=[("X-Original-Method", "POST")] + good).status, 204)
        self.assertEqual(self.verify(broker, cookie, headers=[("X-Original-Method", "HEAD")]).status, 204)

    def test_11_management_requires_admin_qualified_mfa_and_fresh_signed_time(self):
        broker = self.running()
        cookie = self.login(broker)
        self.assertEqual(self.verify(broker, cookie, management=True).status, 204)
        broker.sql("UPDATE log_principaux SET minimum='any' WHERE subject=?", (ALICE,))
        self.assertEqual(self.verify(broker, cookie, management=True).status, 403)
        broker.sql("UPDATE log_principaux SET minimum='mfa', qualified_after=? WHERE subject=?", (int(time.time()) + 60, ALICE))
        self.assertEqual(self.verify(broker, cookie, management=True).status, 403)
        broker.sql("UPDATE log_principaux SET qualified_after=? WHERE subject=?", (int(time.time()) - 2000, ALICE))
        stale = self.login(broker, auth_time=int(time.time()) - 901)
        self.assertEqual(self.verify(broker, stale).status, 204)
        self.assertEqual(self.verify(broker, stale, management=True).status, 403)
        bob = self.login(broker, subject=BOB, mutation="fake_amr")
        self.assertEqual(self.verify(broker, bob, management=True).status, 403)

    def test_12_introspection_outages_preserve_local_session(self):
        broker = self.running()
        cookie = self.login(broker)
        for mode in ("introspection_outage", "introspection_truncated"):
            self.native.mode = mode
            self.assertEqual(self.verify(broker, cookie).status, 503)
            self.assertEqual(broker.sql("SELECT count(*) FROM log_sessions"), [(1,)])
        self.native.mode = None
        self.assertEqual(self.verify(broker, cookie).status, 204)

    def test_13_refresh_rotates_and_distinguishes_outage_from_revocation(self):
        broker = self.running()
        cookie = self.login(broker)
        old = broker.sql("SELECT access,refresh FROM log_sessions")[0]
        self.native.expire_access()
        self.native.mode = "refresh_outage"
        self.assertEqual(self.verify(broker, cookie).status, 503)
        self.assertEqual(broker.sql("SELECT access,refresh FROM log_sessions"), [old])
        self.native.mode = None
        self.assertEqual(self.verify(broker, cookie).status, 204)
        self.assertNotEqual(broker.sql("SELECT access,refresh FROM log_sessions")[0], old)
        self.native.expire_access()
        self.native.mode = "refresh_revoked"
        self.assertEqual(self.verify(broker, cookie).status, 401)
        self.assertEqual(broker.sql("SELECT count(*) FROM log_sessions"), [(0,)])

    def test_14_refresh_cannot_switch_native_subject(self):
        broker = self.running()
        cookie = self.login(broker)
        self.native.expire_access()
        self.native.refresh_mutation = "wrong_subject"
        response = self.verify(broker, cookie)
        self.assertEqual(response.status, 401)
        self.assertFalse(response.values("X-Mrj-User"))
        self.assertEqual(broker.sql("SELECT subject,username FROM log_sessions"), [(ALICE, "synthetic_alice")])

    def test_15_logout_is_local_first_and_preserves_other_session(self):
        broker = self.running()
        alice = self.login(broker)
        bob = self.login(broker, subject=BOB)
        csrf = self.csrf(broker, alice)
        self.native.mode = "revoke_outage"
        response = self.request(broker, "/auth/logout", method="POST", cookie=alice, headers=csrf)
        self.assertIn(response.status, (200, 503))
        self.native.mode = None
        self.assertEqual(self.verify(broker, alice).status, 401)
        self.assertEqual(self.verify(broker, bob).status, 204)

    def test_16_mcp_metadata_and_registration_are_audience_scoped(self):
        broker = self.running()
        for host in HOSTS:
            response = self.request(broker, "/.well-known/oauth-protected-resource/mcp", host=host)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.document()["resource"], "https://" + host + "/mcp")
            self.assertEqual(response.document()["authorization_servers"], ["https://" + host])
            discovery = self.request(broker, "/.well-known/oauth-authorization-server", host=host).document()
            self.assertEqual(discovery["issuer"], "https://" + host)
            self.assertEqual(discovery["code_challenge_methods_supported"], ["S256"])
            self.assertEqual(discovery["token_endpoint_auth_methods_supported"], ["none"])
        before = len(self.native.requests)
        for redirect in ("http://client.example.test/", "https://user@client.example.test/", "https://client.example.test/#fragment"):
            response = self.request(broker, "/oauth/register", method="POST", body={"redirect_uris": [redirect]})
            self.assertEqual(response.status, 400)
        self.assertEqual(len(self.native.requests), before)
        self.register(broker)

    def test_17_mcp_consent_csrf_and_other_session_refusal(self):
        broker = self.running()
        alice, bob = self.login(broker), self.login(broker, subject=BOB)
        client = self.register(broker)
        request = self.consent_request(broker, alice, client)
        response = self.request(broker, "/auth/oauth-demande?" + urlencode({"id": request["id"]}), cookie=alice)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.document()["scope"], "vision:mcp")
        self.assertEqual(self.request(broker, "/auth/oauth-demande?" + urlencode({"id": request["id"]}), cookie=bob).status, 404)
        self.assertEqual(self.consent(broker, bob, request).status, 400)
        self.assertEqual(self.consent(broker, alice, request, headers=[]).status, 403)
        refused = self.consent(broker, alice, request, accepted=False)
        self.assertEqual(refused.status, 200)
        query = parse_qs(urlsplit(refused.document()["redirection"]).query)
        self.assertEqual(query, {"state": ["synthetic-client-state"], "error": ["access_denied"]})
        self.assertEqual(broker.sql("SELECT count(*) FROM log_oauth_codes"), [(0,)])
        self.assertEqual(self.consent(broker, alice, request).status, 400)

    def test_18_mcp_code_pkce_single_use_and_cross_audience(self):
        broker = self.running()
        cookie = self.login(broker)
        client = self.register(broker)
        another_client = self.register(broker)
        request = self.consent_request(broker, cookie, client)
        response = self.consent(broker, cookie, request)
        code = parse_form(urlsplit(response.document()["redirection"]).query.encode())["code"]
        form = {"grant_type": "authorization_code", "client_id": client, "code": code,
                "redirect_uri": "https://client.example.test/return", "code_verifier": request["verifier"]}
        self.assertEqual(self.token_request(broker, dict(form, code_verifier=token())).status, 400)
        self.assertEqual(self.token_request(broker, dict(form, client_id=another_client)).status, 400)
        self.assertEqual(self.token_request(broker, dict(form, redirect_uri="https://another.example.test/")).status, 400)
        self.assertEqual(self.token_request(broker, form, HOSTS[1]).status, 400)
        correct = self.token_request(broker, form)
        self.assertEqual(correct.status, 200)
        tokens = correct.document()
        self.secrets.update((tokens["access_token"], tokens["refresh_token"], code, request["verifier"]))
        self.assertEqual(self.token_request(broker, form).status, 400)
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"]).status, 204)
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"], HOSTS[1]).status, 401)

    def test_19_mcp_refresh_reuse_revokes_whole_family(self):
        broker = self.running()
        cookie = self.login(broker)
        client = self.register(broker)
        tokens, _form = self.issue_mcp(broker, cookie, client)
        refresh = {"grant_type": "refresh_token", "client_id": client, "refresh_token": tokens["refresh_token"]}
        self.assertEqual(self.token_request(broker, refresh, HOSTS[1]).status, 400)
        response = self.token_request(broker, refresh)
        self.assertEqual(response.status, 200)
        newer = response.document()
        self.assertNotEqual(newer["refresh_token"], tokens["refresh_token"])
        self.secrets.update((newer["access_token"], newer["refresh_token"]))
        self.assertEqual(self.mcp_verify(broker, newer["access_token"]).status, 204)
        self.assertEqual(self.token_request(broker, refresh).status, 400)
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"]).status, 401)
        self.assertEqual(self.mcp_verify(broker, newer["access_token"]).status, 401)
        self.assertEqual(self.token_request(broker, dict(refresh, refresh_token=newer["refresh_token"])).status, 400)

    def test_20_mcp_audition_and_parent_logout(self):
        broker = self.running()
        cookie = self.login(broker, HOSTS[1])
        client = self.register(broker, HOSTS[1])
        tokens, _form = self.issue_mcp(broker, cookie, client, HOSTS[1])
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"], HOSTS[1]).status, 204)
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"], HOSTS[0]).status, 401)
        response = self.request(broker, "/auth/logout", method="POST", host=HOSTS[1], cookie=cookie,
                                headers=self.csrf(broker, cookie, HOSTS[1]))
        self.assertEqual(response.status, 200)
        self.assertEqual(self.mcp_verify(broker, tokens["access_token"], HOSTS[1]).status, 401)

    def test_21_tls_and_upstream_redirects_never_bypass_identity(self):
        broker = self.running()
        start = self.begin(broker)
        code = self.native.issue_code(start["location"])
        self.native.mode = "redirect"
        response = self.callback(broker, start, code)
        self.assertIn(response.status, (401, 503))
        self.assertFalse(response.values("X-Mrj-User"))
        self.assertFalse(any(cookie.startswith("__Host-mrj_session=") for cookie in response.values("Set-Cookie")))
        other_crypto = Cryptography(self.case_directory / "untrusted-crypto", OPTIONS.openssl)
        self.native.mode = None
        untrusted = self.launch(configuration_changes={"kanidm_ca_file": str(other_crypto.ca)})
        if untrusted.wait(timeout=3):
            response = self.request(untrusted, "/auth/connexion?retour=%2F")
            if response.status == 302:
                start = {"location": response.header("Location"),
                         "state": parse_form(urlsplit(response.header("Location")).query.encode())["state"],
                         "cookie": response.header("Set-Cookie").split(";", 1)[0], "host": HOSTS[0]}
                response = self.callback(untrusted, start, self.native.issue_code(start["location"]))
            self.assertIn(response.status, (401, 503))
            self.assertFalse(any(cookie.startswith("__Host-mrj_session=") for cookie in response.values("Set-Cookie")))

    def test_22_ambiguous_headers_forms_and_unsafe_returns_refused(self):
        broker = self.running()
        cookie = self.login(broker)
        for headers in ([ ("Cookie", cookie), ("Cookie", cookie) ],
                        [ ("X-Forwarded-Host", HOSTS[0]), ("X-Forwarded-Host", HOSTS[1]) ],
                        [ ("Cookie", cookie + "; " + cookie) ]):
            response = self.verify(broker, cookie, headers=headers)
            self.assertIn(response.status, (400, 401, 403))
            self.assertFalse(response.values("X-Mrj-User"))
        for target in ("https://unrequested.invalid/", "//unrequested.invalid/", "/\\unrequested.invalid/"):
            response = self.request(broker, "/auth/connexion?" + urlencode({"retour": target}))
            self.assertIn(response.status, (400, 401))
            self.assertFalse(response.values("Location"))
        response = self.request(broker, "/oauth/register", method="POST",
                                body=b'{"redirect_uris":["https://client.example.test/"],"redirect_uris":["https://another.example.test/"]}')
        self.assertEqual(response.status, 400)
        response = self.request(broker, "/oauth/token", method="POST", body=b"grant_type=refresh_token&grant_type=authorization_code",
                                headers=[("Content-Type", "application/x-www-form-urlencoded")])
        self.assertEqual(response.status, 400)
        response = self.request(broker, "/oauth/register", method="POST", body=b"x" * 8193)
        self.assertIn(response.status, (400, 413, 415))


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--postgres-bin", required=True, type=Path)
    parser.add_argument("--openssl", required=True)
    parser.add_argument("--output", required=True, type=Path)
    OPTIONS = parser.parse_args()
    OPTIONS.binary = OPTIONS.binary.resolve(strict=True)
    OPTIONS.postgres_bin = OPTIONS.postgres_bin.resolve(strict=True)
    if OPTIONS.output.exists() or OPTIONS.output.is_symlink():
        raise SystemExit("NEW_RESULT_FILE_REQUIRED")
    if not OPTIONS.binary.is_file() or not os.access(OPTIONS.binary, os.X_OK):
        raise SystemExit("EXECUTABLE_REQUIRED")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeIdentityContracts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Report test identifiers and hashes, never response/credential contents.
    receipt = {"schema_version": 1, "scope": "independent-synthetic-native-identity-wire-tests",
               "tests_run": result.testsRun, "passed": result.wasSuccessful(),
               "failed_tests": [test.id() for test, _ in result.failures],
               "error_tests": [test.id() for test, _ in result.errors],
               "skipped_tests": [test.id() for test, _ in result.skipped],
               "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                 for name in ("contract.json", "legacy-state.sql", "principals.sql", "fixture.py", "acceptance.py")},
               "binary_sha256": hashlib.sha256(OPTIONS.binary.read_bytes()).hexdigest(),
               "production_access": False, "protected_policy_adopted": False,
               "actual_kanidm_qualified": False,
               "limits": json.loads((HERE / "contract.json").read_text())["limits"]}
    OPTIONS.output.parent.mkdir(parents=True, exist_ok=True)
    with OPTIONS.output.open("x") as target:
        target.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun == 22 else 1


if __name__ == "__main__":
    raise SystemExit(main())
