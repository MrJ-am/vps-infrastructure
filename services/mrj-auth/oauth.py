"""Autorisation OAuth 2.1 du seul serveur MCP Vision."""
import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

ORIGINE = "https://vision.mrj.am"
RESSOURCE = ORIGINE + "/mcp"
PORTEE = "vision:mcp"
JETON_DUREE = 3600
CODE_DUREE = 300
ACTUALISATION_DUREE = 30 * 86400


def initialiser(sessions):
    with closing(sessions.connect()) as db, db:
        db.executescript("""CREATE TABLE IF NOT EXISTS oauth_clients (
          id TEXT PRIMARY KEY, nom TEXT NOT NULL, redirections TEXT NOT NULL,
          cree INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS oauth_demandes (
          id TEXT PRIMARY KEY, client TEXT NOT NULL, utilisateur TEXT NOT NULL,
          redirection TEXT NOT NULL, etat TEXT NOT NULL, preuve TEXT NOT NULL,
          session TEXT NOT NULL, expiration INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS oauth_codes (
          digest TEXT PRIMARY KEY, client TEXT NOT NULL, utilisateur TEXT NOT NULL,
          redirection TEXT NOT NULL, preuve TEXT NOT NULL, expiration INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS oauth_jetons (
          digest TEXT PRIMARY KEY, client TEXT NOT NULL, utilisateur TEXT NOT NULL,
          type TEXT NOT NULL, expiration INTEGER NOT NULL, revoque INTEGER,
          empreinte TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS oauth_jetons_client ON oauth_jetons(client,utilisateur);""")


def condensat(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def verifier(sessions, autorisation):
    resultat = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{43})", autorisation, re.I)
    if not resultat:
        return None
    with closing(sessions.connect()) as db:
        ligne = db.execute(
            "SELECT utilisateur,expiration,revoque,empreinte FROM oauth_jetons WHERE digest=? AND type='acces'",
            (condensat(resultat[1]),)).fetchone()
    if ligne and ligne["revoque"] is None and ligne["expiration"] > time.time():
        if hmac.compare_digest(ligne["empreinte"], sessions.fingerprint()):
            return ligne["utilisateur"]
    return None


def metadata(suffixe):
    if suffixe.startswith("/.well-known/oauth-protected-resource"):
        return {"resource": RESSOURCE, "authorization_servers": [ORIGINE],
                "scopes_supported": [PORTEE], "bearer_methods_supported": ["header"]}
    return {"issuer": ORIGINE, "authorization_endpoint": ORIGINE + "/oauth/authorize",
            "token_endpoint": ORIGINE + "/oauth/token",
            "registration_endpoint": ORIGINE + "/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [PORTEE]}


def lire_corps(handler, type_attendu, limite=8192):
    if handler.headers.get("Content-Type", "").split(";")[0].strip() != type_attendu:
        raise ValueError("content_type")
    if handler.headers.get("Transfer-Encoding"):
        raise ValueError("transfer_encoding")
    longueur = int(handler.headers.get("Content-Length", "0"))
    if not 0 < longueur <= limite:
        raise ValueError("length")
    return handler.rfile.read(longueur).decode("utf-8")


def unique(parametres, cle, defaut=None):
    valeurs = parametres.get(cle)
    if valeurs is None:
        return defaut
    if len(valeurs) != 1:
        raise ValueError("duplicate_parameter")
    return valeurs[0]


def erreur(handler, code, message):
    handler.reply(code, {"error": message})
    return True


def redirection_valide(valeur):
    if not isinstance(valeur, str) or len(valeur) > 1024:
        return False
    u = urlsplit(valeur)
    return u.scheme == "https" and bool(u.hostname) and not u.username and not u.password and not u.fragment


def rediriger(handler, adresse):
    handler.send_response(302)
    handler.send_header("Location", adresse)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Content-Length", "0")
    handler.end_headers()
    return True


def page(handler, contenu):
    donnees = contenu.encode("utf-8")
    handler.send_response(200)
    for cle, valeur in {
        "Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(donnees)),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    }.items():
        handler.send_header(cle, valeur)
    handler.end_headers()
    handler.wfile.write(donnees)
    return True


def enregistrer(handler, sessions):
    try:
        donnees = json.loads(lire_corps(handler, "application/json"))
        redirections = donnees["redirect_uris"]
        nom = donnees.get("client_name", "Client MCP")
        if not isinstance(redirections, list) or not 1 <= len(redirections) <= 5:
            raise ValueError("redirect_uris")
        if not all(redirection_valide(u) for u in redirections):
            raise ValueError("redirect_uris")
        if not isinstance(nom, str) or not 1 <= len(nom) <= 100:
            raise ValueError("client_name")
        if donnees.get("token_endpoint_auth_method", "none") != "none":
            raise ValueError("token_endpoint_auth_method")
        if not set(donnees.get("grant_types", ["authorization_code"])).issubset(
                {"authorization_code", "refresh_token"}):
            raise ValueError("grant_types")
        identifiant = secrets.token_urlsafe(24)
        with closing(sessions.connect()) as db, db:
            if db.execute("SELECT count(*) FROM oauth_clients").fetchone()[0] >= 2000:
                return erreur(handler, 429, "registration_limited")
            db.execute("INSERT INTO oauth_clients VALUES (?,?,?,?)",
                       (identifiant, nom, json.dumps(redirections), int(time.time())))
        handler.reply(201, {"client_id": identifiant, "client_name": nom,
                            "redirect_uris": redirections,
                            "token_endpoint_auth_method": "none",
                            "grant_types": ["authorization_code", "refresh_token"],
                            "response_types": ["code"]})
    except (ValueError, KeyError, TypeError):
        return erreur(handler, 400, "invalid_client_metadata")
    return True


def demande(handler, sessions):
    try:
        q = parse_qs(urlsplit(handler.path).query, keep_blank_values=True)
        client, retour = unique(q, "client_id"), unique(q, "redirect_uri")
        etat, preuve = unique(q, "state", ""), unique(q, "code_challenge")
        if (unique(q, "response_type") != "code" or
            unique(q, "code_challenge_method") != "S256" or
            unique(q, "resource", RESSOURCE) != RESSOURCE or
            unique(q, "scope", PORTEE) != PORTEE or
            not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", preuve or "") or
            len(etat) > 1024):
            raise ValueError("invalid_request")
        with closing(sessions.connect()) as db:
            ligne = db.execute("SELECT * FROM oauth_clients WHERE id=?", (client,)).fetchone()
        if ligne is None or retour not in json.loads(ligne["redirections"]):
            raise ValueError("invalid_client")
        session = sessions.session(handler.headers.get("Cookie", ""))
        if not session:
            return page(handler, """<!doctype html><html lang="fr"><meta charset="utf-8">
              <meta name="viewport" content="width=device-width,initial-scale=1">
              <title>Connexion Vision</title><body style="font:18px system-ui;max-width:35em;margin:3em auto;padding:1em">
              <h1>Connectez-vous à Vision</h1><p>La connexion est nécessaire avant d’autoriser le client MCP.</p>
              <form id="connexion"><label>Identifiant <input name="username" required></label>
              <label>Mot de passe <input name="password" type="password" required></label>
              <button>Se connecter</button></form><p id="etat" role="status"></p>
              <script src="/auth/oauth.js" defer></script></body></html>""")
        identifiant = secrets.token_urlsafe(24)
        with closing(sessions.connect()) as db, db:
            db.execute("DELETE FROM oauth_demandes WHERE expiration<?", (int(time.time()),))
            db.execute("INSERT INTO oauth_demandes VALUES (?,?,?,?,?,?,?,?)",
                       (identifiant, client, session["username"], retour, etat, preuve,
                        condensat(sessions.token(handler.headers.get("Cookie", ""))),
                        int(time.time()) + CODE_DUREE))
        titre = html.escape(ligne["nom"])
        domaine = html.escape(urlsplit(retour).hostname)
        return page(handler, f"""<!doctype html><html lang="fr"><meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Autoriser l’accès à Vision</title>
          <body style="font:18px/1.5 system-ui;color:#193d38;background:#eef7f3;max-width:38em;margin:2em auto;padding:1em">
          <main style="background:white;border-radius:16px;padding:1.5em">
          <h1>Autoriser {titre} ?</h1>
          <p>Ce client pourra lire et modifier toutes vos fiches Vision via MCP.
          Après votre décision, vous serez renvoyé vers {domaine}.</p>
          <form method="post" action="/oauth/authorize">
          <input type="hidden" name="request_id" value="{identifiant}">
          <input type="hidden" name="csrf" value="{html.escape(session['csrf'])}">
          <button name="decision" value="autoriser">Autoriser</button>
          <button name="decision" value="refuser">Refuser</button></form></main></body></html>""")
    except (ValueError, TypeError):
        return erreur(handler, 400, "invalid_request")


def consentir(handler, sessions):
    session = sessions.session(handler.headers.get("Cookie", ""))
    if not session or handler.headers.get("Origin") != ORIGINE:
        return erreur(handler, 403, "invalid_origin")
    try:
        q = parse_qs(lire_corps(handler, "application/x-www-form-urlencoded"),
                     keep_blank_values=True)
        identifiant, decision = unique(q, "request_id"), unique(q, "decision")
        if (not hmac.compare_digest(unique(q, "csrf", ""), session["csrf"]) or
            decision not in ("autoriser", "refuser")):
            raise ValueError("invalid_consent")
        with closing(sessions.connect()) as db, db:
            ligne = db.execute("SELECT * FROM oauth_demandes WHERE id=?", (identifiant,)).fetchone()
            if (ligne is None or ligne["utilisateur"] != session["username"] or
                ligne["session"] != condensat(sessions.token(handler.headers.get("Cookie", ""))) or
                ligne["expiration"] <= time.time()):
                raise ValueError("expired_request")
            db.execute("DELETE FROM oauth_demandes WHERE id=?", (identifiant,))
            if decision == "autoriser":
                code = secrets.token_urlsafe(32)
                db.execute("INSERT INTO oauth_codes VALUES (?,?,?,?,?,?)",
                           (condensat(code), ligne["client"], ligne["utilisateur"],
                            ligne["redirection"], ligne["preuve"], int(time.time()) + CODE_DUREE))
        parametres = {"state": ligne["etat"]}
        if decision == "autoriser":
            parametres["code"] = code
        else:
            parametres["error"] = "access_denied"
        separateur = "&" if urlsplit(ligne["redirection"]).query else "?"
        return rediriger(handler, ligne["redirection"] + separateur + urlencode(parametres))
    except (ValueError, TypeError):
        return erreur(handler, 400, "invalid_request")


def creer_jeton(db, sessions, client, utilisateur, type_, duree):
    secret = secrets.token_urlsafe(32)
    db.execute("INSERT INTO oauth_jetons VALUES (?,?,?,?,?,NULL,?)",
               (condensat(secret), client, utilisateur, type_, int(time.time()) + duree,
                sessions.fingerprint()))
    return secret


def jeton(handler, sessions):
    try:
        q = parse_qs(lire_corps(handler, "application/x-www-form-urlencoded"),
                     keep_blank_values=True)
        client = unique(q, "client_id")
        with closing(sessions.connect()) as db, db:
            if not db.execute("SELECT 1 FROM oauth_clients WHERE id=?", (client,)).fetchone():
                raise ValueError("invalid_client")
            type_ = unique(q, "grant_type")
            if type_ == "authorization_code":
                code = unique(q, "code", "")
                ligne = db.execute("SELECT * FROM oauth_codes WHERE digest=?",
                                   (condensat(code),)).fetchone()
                preuve = unique(q, "code_verifier", "")
                if (ligne is None or ligne["client"] != client or
                    ligne["redirection"] != unique(q, "redirect_uri") or
                    ligne["expiration"] <= time.time() or
                    not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", preuve)):
                    raise ValueError("invalid_grant")
                calcul = base64.urlsafe_b64encode(hashlib.sha256(preuve.encode()).digest()).rstrip(b"=").decode()
                if not hmac.compare_digest(calcul, ligne["preuve"]):
                    raise ValueError("invalid_grant")
                db.execute("DELETE FROM oauth_codes WHERE digest=?", (condensat(code),))
            elif type_ == "refresh_token":
                secret = unique(q, "refresh_token", "")
                ligne = db.execute("SELECT * FROM oauth_jetons WHERE digest=? AND type='actualisation'",
                                   (condensat(secret),)).fetchone()
                if (ligne is None or ligne["client"] != client or ligne["revoque"] is not None or
                    ligne["expiration"] <= time.time() or
                    not hmac.compare_digest(ligne["empreinte"], sessions.fingerprint())):
                    raise ValueError("invalid_grant")
                db.execute("UPDATE oauth_jetons SET revoque=? WHERE digest=?",
                           (int(time.time()), condensat(secret)))
            else:
                raise ValueError("unsupported_grant_type")
            utilisateur = ligne["utilisateur"]
            acces = creer_jeton(db, sessions, client, utilisateur, "acces", JETON_DUREE)
            actualisation = creer_jeton(db, sessions, client, utilisateur,
                                       "actualisation", ACTUALISATION_DUREE)
        handler.reply(200, {"access_token": acces, "token_type": "Bearer",
                            "expires_in": JETON_DUREE, "refresh_token": actualisation,
                            "scope": PORTEE})
    except (ValueError, TypeError):
        return erreur(handler, 400, "invalid_grant")
    return True


def connexions(handler, sessions):
    session = sessions.session(handler.headers.get("Cookie", ""))
    if not session:
        return erreur(handler, 401, "authentication_required")
    if handler.command == "POST":
        if (handler.headers.get("Origin") != ORIGINE or
            not hmac.compare_digest(handler.headers.get("X-CSRF-Token", ""), session["csrf"])):
            return erreur(handler, 403, "csrf_required")
        try:
            corps = json.loads(lire_corps(handler, "application/json"))
            if set(corps) != {"client_id"} or not isinstance(corps["client_id"], str):
                raise ValueError("invalid_request")
            with closing(sessions.connect()) as db, db:
                db.execute("UPDATE oauth_jetons SET revoque=? WHERE client=? AND utilisateur=? AND revoque IS NULL",
                           (int(time.time()), corps["client_id"], session["username"]))
        except (ValueError, TypeError):
            return erreur(handler, 400, "invalid_request")
    with closing(sessions.connect()) as db:
        lignes = db.execute(
            """SELECT c.id,c.nom,max(j.expiration) AS expiration
               FROM oauth_jetons j JOIN oauth_clients c ON c.id=j.client
               WHERE j.utilisateur=? AND j.revoque IS NULL AND j.expiration>?
               GROUP BY c.id,c.nom ORDER BY c.nom""",
            (session["username"], int(time.time()))).fetchall()
    handler.reply(200, {"connections": [
        {"clientId": ligne["id"], "name": ligne["nom"], "expiresAt": ligne["expiration"]}
        for ligne in lignes]})
    return True


def traiter(handler, sessions, host):
    chemin = urlsplit(handler.path).path
    if host != "vision.mrj.am":
        return False
    if chemin in ("/.well-known/oauth-protected-resource",
                  "/.well-known/oauth-protected-resource/mcp",
                  "/.well-known/oauth-authorization-server") and handler.command == "GET":
        handler.reply(200, metadata(chemin))
        return True
    if chemin == "/oauth/register" and handler.command == "POST":
        return enregistrer(handler, sessions)
    if chemin == "/oauth/authorize":
        if handler.command == "GET":
            return demande(handler, sessions)
        if handler.command == "POST":
            return consentir(handler, sessions)
    if chemin == "/oauth/token" and handler.command == "POST":
        return jeton(handler, sessions)
    if chemin == "/auth/oauth-connections" and handler.command in ("GET", "POST"):
        return connexions(handler, sessions)
    if chemin == "/auth/oauth.js" and handler.command == "GET":
        script = ("""document.querySelector('#connexion').onsubmit = async e => {
          e.preventDefault();
          const f = new FormData(e.target);
          const r = await fetch('/auth/login', {method:'POST',credentials:'same-origin',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({username:f.get('username'),password:f.get('password')})});
          if (r.ok) location.reload();
          else document.querySelector('#etat').textContent='Connexion refusée.';
        };""").encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/javascript; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(script)))
        handler.end_headers()
        handler.wfile.write(script)
        return True
    return False
