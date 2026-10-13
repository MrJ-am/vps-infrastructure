(in-package #:mrjam-log)

;; Audience bornée à la requête centrale. Les grants sont liés à une session
;; host-only ; verifier/jetons exigent la session de cette audience à chaque appel.
;; Vision garde la valeur historique par défaut et les grants existants.
(defvar *hote-mcp* "vision.mrj.am")
(defun origine-mcp ()
  (unless (member *hote-mcp* '("vision.mrj.am" "audition.mrj.am") :test #'equal) (refuser 403))
  (concatenate 'string "https://" *hote-mcp*))
(defun url-mcp () (concatenate 'string (origine-mcp) "/mcp"))
(defun scope-mcp () (if (equal *hote-mcp* "audition.mrj.am") "audition:mcp" "vision:mcp"))

(defun initialiser-oauth (c)
  "Adaptateur du contrat OAuth MCP existant ; aucun compte ni authentificateur."
  (base c (lambda (db)
    (dolist (sql '("CREATE TABLE IF NOT EXISTS log_oauth_clients (id TEXT PRIMARY KEY, name TEXT NOT NULL, redirects TEXT NOT NULL, created INTEGER NOT NULL)"
                   "CREATE TABLE IF NOT EXISTS log_oauth_requests (id TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL, redirect TEXT NOT NULL, state TEXT NOT NULL, challenge TEXT NOT NULL, expires INTEGER NOT NULL)"
                   "CREATE TABLE IF NOT EXISTS log_oauth_codes (digest TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL, redirect TEXT NOT NULL, challenge TEXT NOT NULL, expires INTEGER NOT NULL)"
                   "CREATE TABLE IF NOT EXISTS log_oauth_tokens (digest TEXT PRIMARY KEY, client TEXT NOT NULL, session TEXT NOT NULL, kind TEXT NOT NULL, expires INTEGER NOT NULL, revoked INTEGER, family TEXT NOT NULL)"))
      (mrjam-native:sqlite-requete db sql))))
  c)

(defun redirect-mcp-p (uri)
  ;; Pas de récupération réseau/CIMD/SSRF. Redirections HTTPS exactes du client.
  (and (mrjam-oidc::texte-borne-p uri 9 1024) (uiop:string-prefix-p "https://" uri)
       (every (lambda (x) (<= 33 (char-code x) 126)) uri)
       (not (find #\# uri)) (not (find #\\ uri))
       (let ((authority (subseq uri 8 (or (position #\/ uri :start 8)
                                         (position #\? uri :start 8) (length uri)))))
         (and (> (length authority) 0) (not (find #\@ authority))
              (every (lambda (x) (or (alphanumericp x) (find x ".-:"))) authority)))))

(defun enregistrer-client (c document &optional (maintenant (temps)))
  (let ((uris (j document "redirect_uris")) (name (or (j document "client_name") "Client MCP")))
    (unless (and (vision:json-array-p uris) (<= 1 (length (vision:json-array-items uris)) 5)
                 (every #'redirect-mcp-p (vision:json-array-items uris))
                 (mrjam-oidc::texte-borne-p name 1 80)
                 (or (null (j document "token_endpoint_auth_method"))
                     (equal (j document "token_endpoint_auth_method") "none"))) (refuser 400))
    (let ((id (mrjam-native:aleatoire-url)))
      (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
        (when (>= (champ (first (mrjam-native:sqlite-requete db "SELECT count(*) AS n FROM log_oauth_clients")) "n") 2048) (refuser 429))
        (mrjam-native:sqlite-requete db "INSERT INTO log_oauth_clients VALUES(?,?,?,?)"
          (list id name (vision:json-encode uris) maintenant))))))
      (vision:jobject "client_id" id "client_name" name "redirect_uris" uris
        "token_endpoint_auth_method" "none" "grant_types" (vision:jarray "authorization_code" "refresh_token")
        "response_types" (vision:jarray "code")))))

(defun metadata-mcp (&optional resource)
  (if resource
      (vision:jobject "resource" (url-mcp)
        "authorization_servers" (vision:jarray (origine-mcp))
        "scopes_supported" (vision:jarray (scope-mcp)) "bearer_methods_supported" (vision:jarray "header"))
      (vision:jobject "issuer" (origine-mcp)
        "authorization_endpoint" (concatenate 'string (origine-mcp) "/oauth/authorize")
        "token_endpoint" (concatenate 'string (origine-mcp) "/oauth/token")
        "registration_endpoint" (concatenate 'string (origine-mcp) "/oauth/register")
        "revocation_endpoint" (concatenate 'string (origine-mcp) "/oauth/revoke")
        "response_types_supported" (vision:jarray "code")
        "grant_types_supported" (vision:jarray "authorization_code" "refresh_token")
        "code_challenge_methods_supported" (vision:jarray "S256")
        "token_endpoint_auth_methods_supported" (vision:jarray "none")
        "scopes_supported" (vision:jarray (scope-mcp)))))

(defun demander-mcp (c cookies query &optional (maintenant (temps)))
  (let* ((session (session c *hote-mcp* cookies maintenant))
         (client (j query "client_id")) (redirect (j query "redirect_uri"))
         (state (j query "state")) (challenge (j query "code_challenge"))
         (id (mrjam-native:aleatoire-url)))
    (unless session (refuser))
    (unless (and (equal (j query "response_type") "code") (equal (j query "code_challenge_method") "S256")
                 (mrjam-oidc::secret-url-p challenge) (mrjam-oidc::texte-borne-p state 1 1024)
                 (equal (j query "scope") (scope-mcp))
                 (member (j query "resource") (list nil (url-mcp)) :test #'equal)) (refuser 400))
    (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
      (let ((row (first (mrjam-native:sqlite-requete db "SELECT * FROM log_oauth_clients WHERE id=?" (list client)))))
        (unless (and row (member redirect (vision:json-array-items (vision:parse-json (champ row "redirects"))) :test #'equal)) (refuser 400)))
      (mrjam-native:sqlite-requete db "DELETE FROM log_oauth_requests WHERE expires<=?" (list maintenant))
      (when (>= (champ (first (mrjam-native:sqlite-requete db "SELECT count(*) AS n FROM log_oauth_requests")) "n") 4096) (refuser 429))
      (mrjam-native:sqlite-requete db "INSERT INTO log_oauth_requests VALUES(?,?,?,?,?,?,?)"
        (list id client (mrjam-native:sha256 (token-cookie cookies "__Host-mrj_session")) redirect state challenge (+ maintenant 600)))))))
    id))

(defun lire-demande-mcp (c cookies id &optional (maintenant (temps)))
  (unless (session c *hote-mcp* cookies maintenant) (refuser))
  (let ((row (base c (lambda (db) (first (mrjam-native:sqlite-requete db
       "SELECT r.id,c.name,r.redirect FROM log_oauth_requests r JOIN log_oauth_clients c ON c.id=r.client WHERE r.id=? AND r.session=? AND r.expires>?"
       (list id (mrjam-native:sha256 (token-cookie cookies "__Host-mrj_session")) maintenant)))))))
    (unless row (refuser 404))
    (vision:jobject "id" (champ row "id") "client" (champ row "name") "redirect_uri" (champ row "redirect")
                    "scope" (scope-mcp))))

(defun consentir-mcp (c cookies id accepter &optional (maintenant (temps)))
  (unless (session c *hote-mcp* cookies maintenant) (refuser))
  (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
    (let ((row (first (mrjam-native:sqlite-requete db "SELECT * FROM log_oauth_requests WHERE id=? AND session=? AND expires>?"
                 (list id (mrjam-native:sha256 (token-cookie cookies "__Host-mrj_session")) maintenant))))
          (code (mrjam-native:aleatoire-url)))
      (unless row (refuser 400))
      (mrjam-native:sqlite-requete db "DELETE FROM log_oauth_requests WHERE id=?" (list id))
      (when accepter (mrjam-native:sqlite-requete db "INSERT INTO log_oauth_codes VALUES(?,?,?,?,?,?)"
        (list (mrjam-native:sha256 code) (champ row "client") (champ row "session") (champ row "redirect") (champ row "challenge") (+ maintenant 300))))
      (concatenate 'string (champ row "redirect") (if (find #\? (champ row "redirect")) "&" "?")
        (mrjam-oidc::formulaire-oidc
          (list (cons "state" (champ row "state"))
                (if accepter (cons "code" code) (cons "error" "access_denied")))))))))))

(defun creer-paire-mcp (db client parent famille maintenant)
  (let* ((access (mrjam-native:aleatoire-url)) (refresh (mrjam-native:aleatoire-url))
         (parent-exp (champ (first (mrjam-native:sqlite-requete db "SELECT expires FROM log_sessions WHERE digest=?" (list parent))) "expires"))
         (duree-access (and parent-exp (min 3600 (- parent-exp maintenant)))))
    (unless (and duree-access (> duree-access 0)) (refuser 400))
    (loop for secret in (list access refresh) for kind in '("access" "refresh")
          for duree in (list duree-access (min (* 30 86400) (- parent-exp maintenant))) do
      (mrjam-native:sqlite-requete db "INSERT INTO log_oauth_tokens VALUES(?,?,?,?,?,NULL,?)"
        (list (mrjam-native:sha256 secret) client parent kind (+ maintenant duree) famille)))
    (vision:jobject "access_token" access "refresh_token" refresh "token_type" "Bearer"
                    "expires_in" duree-access "scope" (scope-mcp))))

(defun jetons-mcp (c query &optional (maintenant (temps)))
  (let* ((client (j query "client_id")) (grant (j query "grant_type"))
         (secret (if (equal grant "authorization_code") (j query "code") (j query "refresh_token")))
         (table (if (equal grant "authorization_code") "log_oauth_codes" "log_oauth_tokens")))
    (unless (and (member grant '("authorization_code" "refresh_token") :test #'equal)
                 (mrjam-oidc::secret-url-p secret)
                 (member (j query "resource") (list nil (url-mcp)) :test #'equal)) (refuser 400))
    ;; Authentification native hors verrou SQLite ; puis relecture atomique
    ;; du grant pour consommation/rotation. Les entrées restent bornées.
    (let* ((digest (mrjam-native:sha256 secret))
           (row (base c (lambda (db) (first (mrjam-native:sqlite-requete db
                    (concatenate 'string "SELECT * FROM " table " WHERE digest=? AND client=?") (list digest client)))))))
      (unless (and row (> (champ row "expires") maintenant)
                   (or (equal grant "authorization_code") (equal (champ row "kind") "refresh"))
                   (session-digest c *hote-mcp* (champ row "session") maintenant)) (refuser 400))
      (when (equal grant "authorization_code")
        (let ((verifier (j query "code_verifier")))
          (unless (and (mrjam-oidc::texte-borne-p verifier 43 128)
                       (every (lambda (x) (or (alphanumericp x) (find x "._~-"))) verifier)
                       (equal (j query "redirect_uri") (champ row "redirect"))
                       (mrjam-native:secret-egal-p (champ row "challenge")
                         (mrjam-native:base64 (mrjam-native::digest-octets (mrjam-native::octets verifier)) :url t :sans-remplissage t)))
            (refuser 400))))
      (let ((result (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
        (let ((current (first (mrjam-native:sqlite-requete db
                          (concatenate 'string "SELECT * FROM " table " WHERE digest=? AND client=?") (list digest client)))))
          (unless current (refuser 400))
          (if (and (equal grant "refresh_token") (not (eq :null (champ current "revoked"))))
              (progn
                (mrjam-native:sqlite-requete db "UPDATE log_oauth_tokens SET revoked=? WHERE family=?" (list maintenant (champ current "family")))
                nil) ; Commit de la révocation de famille avant refus extérieur.
              (let ((famille (if (equal grant "authorization_code") (mrjam-native:aleatoire-url) (champ current "family"))))
                (if (equal grant "authorization_code")
                    (mrjam-native:sqlite-requete db "DELETE FROM log_oauth_codes WHERE digest=?" (list digest))
                    (mrjam-native:sqlite-requete db "UPDATE log_oauth_tokens SET revoked=? WHERE digest=?" (list maintenant digest)))
                (creer-paire-mcp db client (champ current "session") famille maintenant))))))))))
        (or result (refuser 400))))))

(defun session-mcp (c authorization &optional (maintenant (temps)))
  (when (and (stringp authorization) (>= (length authorization) 7) (string-equal "Bearer " authorization :end2 7)
             (mrjam-oidc::secret-url-p (subseq authorization 7)))
    (let ((row (base c (lambda (db) (first (mrjam-native:sqlite-requete db
                  "SELECT session FROM log_oauth_tokens WHERE digest=? AND kind='access' AND revoked IS NULL AND expires>?"
                  (list (mrjam-native:sha256 (subseq authorization 7)) maintenant)))))))
      (when row (session-digest c *hote-mcp* (champ row "session") maintenant)))))

(defun verifier-mcp (c authorization &optional (maintenant (temps)))
  (champ (session-mcp c authorization maintenant) "username"))

(defun revoquer-mcp (c client token &optional (maintenant (temps)))
  (unless (mrjam-oidc::secret-url-p token) (refuser 400))
  (base c (lambda (db) (mrjam-native:sqlite-requete db
    "UPDATE log_oauth_tokens SET revoked=? WHERE client=? AND family IN (SELECT family FROM log_oauth_tokens WHERE digest=? AND client=?)"
    (list maintenant client (mrjam-native:sha256 token) client))))
  t)
