-- Invented empty fixture using the public schema from the pinned Log source.
CREATE TABLE log_transactions (
 state TEXT PRIMARY KEY, binding TEXT NOT NULL, client_id TEXT NOT NULL,
 host TEXT NOT NULL, verifier TEXT NOT NULL, nonce TEXT NOT NULL,
 retour TEXT NOT NULL, expires INTEGER NOT NULL, stepup INTEGER NOT NULL
 CHECK(stepup IN (0,1)), invitation TEXT, notice TEXT);
CREATE TABLE log_sessions (
 digest TEXT PRIMARY KEY, host TEXT NOT NULL, subject TEXT NOT NULL,
 username TEXT NOT NULL, csrf TEXT NOT NULL, created INTEGER NOT NULL,
 seen INTEGER NOT NULL, expires INTEGER NOT NULL, auth_time INTEGER NOT NULL,
 access TEXT NOT NULL, refresh TEXT NOT NULL, nonce TEXT NOT NULL);
CREATE TABLE log_principaux (
 subject TEXT PRIMARY KEY, mail TEXT UNIQUE NOT NULL,
 duration INTEGER NOT NULL CHECK(duration IN (604800,2592000,7776000)),
 minimum TEXT NOT NULL CHECK(minimum IN ('any','mfa')), qualified_after INTEGER NOT NULL);
CREATE TABLE log_oauth_clients (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, redirects TEXT NOT NULL, created INTEGER NOT NULL);
CREATE TABLE log_oauth_requests (
 id TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL,
 redirect TEXT NOT NULL, state TEXT NOT NULL, challenge TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE log_oauth_codes (
 digest TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL,
 redirect TEXT NOT NULL, challenge TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE log_oauth_tokens (
 digest TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL,
 kind TEXT NOT NULL, expires INTEGER NOT NULL, revoked INTEGER, family TEXT NOT NULL);
