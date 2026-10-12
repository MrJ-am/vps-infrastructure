(in-package #:mrjam-log)

(defstruct (contexte (:constructor %contexte)) chemin clients identifier
  (verrou (sb-thread:make-mutex :name "renouvellements Log")))
(defmethod print-object ((c contexte) s)
  (print-unreadable-object (c s :type t) (write-string "configuration masquée" s)))

(defun faire-contexte (chemin clients identifier)
  "CLIENTS associe hôte configuré et client OIDC. IDENTIFIER vérifie le compte
métier à chaque accès ; aucun raccordement implicite par adresse électronique."
  (unless (and (uiop:absolute-pathname-p chemin) (functionp identifier)
               (consp clients) (<= (length clients) 8)
               (every (lambda (p) (and (consp p) (mrjam-oidc::hote-applicatif-p (car p))
                                      (typep (cdr p) 'mrjam-oidc::client-oidc))) clients)
               (= (length clients) (length (remove-duplicates clients :key #'car :test #'equal))))
    (refuser 503))
  (%contexte :chemin chemin :clients clients :identifier identifier))

(defun client (c hote)
  (or (cdr (assoc hote (contexte-clients c) :test #'equal)) (refuser 403)))
(defun base (c f) (mrjam-native:avec-sqlite (contexte-chemin c) f))
(defun initialiser (c)
  "Migration additive explicite au démarrage, jamais au chargement ASDF."
  (mrjam-oidc:initialiser-transactions (contexte-chemin c))
  (base c (lambda (db)
    (mrjam-native:sqlite-requete db
      "CREATE TABLE IF NOT EXISTS log_sessions (digest TEXT PRIMARY KEY, host TEXT NOT NULL,
       subject TEXT NOT NULL, username TEXT NOT NULL, csrf TEXT NOT NULL,
       created INTEGER NOT NULL, seen INTEGER NOT NULL, expires INTEGER NOT NULL,
       auth_time INTEGER NOT NULL, access TEXT NOT NULL, refresh TEXT NOT NULL,
       nonce TEXT NOT NULL)")
    ;; Configuration privée établie par l'opérateur, jamais par le navigateur.
    ;; Le sujet reste un UUID, indépendamment des noms et adresses modifiables.
    (mrjam-native:sqlite-requete db
      "CREATE TABLE IF NOT EXISTS log_principaux (subject TEXT PRIMARY KEY,
       mail TEXT UNIQUE NOT NULL, duration INTEGER NOT NULL CHECK(duration IN (604800,2592000,7776000)),
       minimum TEXT NOT NULL CHECK(minimum IN ('any','mfa')), qualified_after INTEGER NOT NULL)")))
  c)

(defun cookie (nom valeur duree)
  (unless (or (equal valeur "") (mrjam-oidc::secret-url-p valeur)) (refuser 400))
  ;; Host-only : une application sœur ne peut établir une session d'un autre client.
  (format nil "~A=~A; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=~D" nom valeur duree))
(defun cookie-session (valeur &optional (duree (* 7 86400)))
  (cookie "__Host-mrj_session" valeur duree))
(defun cookie-transaction (valeur &optional (duree 600))
  (cookie "__Host-mrj_oidc" valeur duree))
(defun token-cookie (texte nom)
  (when (stringp texte)
    (let ((trouve nil))
      (dolist (part (uiop:split-string texte :separator ";"))
        (let* ((p (string-trim '(#\Space #\Tab) part)) (equal-pos (position #\= p)))
          (when (and equal-pos (equal (subseq p 0 equal-pos) nom))
            (when trouve (refuser))
            (setf trouve (subseq p (1+ equal-pos))))))
      (when (and trouve (mrjam-oidc::secret-url-p trouve)) trouve))))

(defun demarrer (c hote retour &optional (maintenant (temps)))
  (let* ((client (client c hote))
         (d (mrjam-oidc:demarrer-transaction (contexte-chemin c)
               (mrjam-oidc::client-oidc-id client) hote maintenant :retour retour)))
    (values
      (concatenate 'string "https://log.mrj.am/ui/oauth2?"
        (mrjam-oidc::formulaire-oidc
          (list (cons "client_id" (mrjam-oidc::client-oidc-id client))
                (cons "response_type" "code") (cons "scope" "openid email profile")
                (cons "redirect_uri" (concatenate 'string "https://" hote "/auth/retour"))
                (cons "state" (mrjam-oidc:demarrage-state d))
                (cons "nonce" (mrjam-oidc:demarrage-nonce d))
                (cons "code_challenge" (mrjam-oidc:demarrage-challenge d))
                (cons "code_challenge_method" "S256"))))
      (cookie-transaction (mrjam-oidc:demarrage-binding d)))))

(defun principal (c issuer subject)
  (let ((p (funcall (contexte-identifier c) issuer subject)))
    (unless (and (eq (j p "actif") :true) (not (j p "erreur"))
                 (mrjam-oidc::texte-borne-p (j p "utilisateur") 1 64)) (refuser 403))
    p))
(defun document-token (r)
  (unless (= 200 (mrjam-oidc:reponse-oidc-statut r)) (refuser))
  (let ((d (mrjam-oidc:reponse-oidc-document r)))
    (dolist (cle '("access_token" "refresh_token" "id_token"))
      (unless (mrjam-oidc::texte-borne-p (j d cle) 1 32768) (refuser 503)))
    d))

(defun retour (c hote state code cookie &optional (maintenant (temps)))
  (let* ((client (client c hote))
         (binding (token-cookie cookie "__Host-mrj_oidc"))
         (transaction (mrjam-oidc:consommer-transaction (contexte-chemin c)
           state binding (mrjam-oidc::client-oidc-id client) hote maintenant))
         ;; Consommation avant HTTP : un timeout ne rend jamais le code rejouable.
         (d (document-token (mrjam-oidc:echanger-code client code (champ transaction "verifier") hote)))
         (id (mrjam-oidc:verifier-id-token (j d "id_token") (mrjam-oidc:lire-jwks client)
               :client-id (mrjam-oidc::client-oidc-id client) :nonce (champ transaction "nonce")
               :maintenant maintenant :access-token (j d "access_token")))
         (p (principal c (mrjam-oidc:identite-issuer id) (mrjam-oidc:identite-sujet id)))
         (token (mrjam-native:aleatoire-url)) (csrf (mrjam-native:aleatoire-url)))
    (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
      (mrjam-native:sqlite-requete db "DELETE FROM log_sessions WHERE expires<=?" (list maintenant))
      (when (>= (champ (first (mrjam-native:sqlite-requete db
                    "SELECT count(*) AS nombre FROM log_sessions WHERE username=?" (list (j p "utilisateur")))) "nombre") 20)
        (refuser 429))
      (mrjam-native:sqlite-requete db "INSERT INTO log_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        (list (mrjam-native:sha256 token) hote (mrjam-oidc:identite-sujet id) (j p "utilisateur") csrf
              maintenant maintenant (+ maintenant (duree-session c (mrjam-oidc:identite-sujet id))) (mrjam-oidc:identite-auth-time id)
              (j d "access_token") (j d "refresh_token") (champ transaction "nonce")))))))
    (values (champ transaction "retour")
            (cookie-session token (duree-session c (mrjam-oidc:identite-sujet id)))
            (cookie-transaction "" 0))))

(defun session (c hote cookies &optional (maintenant (temps)))
  (let ((secret (token-cookie cookies "__Host-mrj_session")))
    (when secret (session-digest c hote (mrjam-native:sha256 secret) maintenant))))

(defun session-digest (c hote digest &optional (maintenant (temps)))
  "Chemin interne du broker MCP : DIGEST provient de sa base, jamais d'un header."
  (unless (and (stringp digest) (= 64 (length digest))
               (every (lambda (x) (find x "0123456789abcdef")) digest)) (refuser))
  (let ((client (client c hote)))
    ;; Une seule image produit : sérialiser rotation/révocation d'une session.
    (sb-thread:with-mutex ((contexte-verrou c))
      (let ((row (base c (lambda (db) (first (mrjam-native:sqlite-requete db
                    "SELECT * FROM log_sessions WHERE digest=? AND host=? AND expires>?"
                    (list digest hote maintenant)))))))
        (unless row (return-from session-digest nil))
        (let* ((issuer (mrjam-oidc:issuer-client (mrjam-oidc::client-oidc-id client)))
               (p (principal c issuer (champ row "subject")))
               (r (mrjam-oidc:introspecter-jeton client (champ row "access")))
               (d (mrjam-oidc:reponse-oidc-document r)))
          (unless (equal (j p "utilisateur") (champ row "username")) (refuser 403))
          (when (and (= 200 (mrjam-oidc:reponse-oidc-statut r))
                     (or (not (eq :true (j d "active")))
                         (and (integerp (j d "exp")) (<= (j d "exp") (+ maintenant 60)))))
            (let* ((tokens (document-token (mrjam-oidc:renouveler-jetons client (champ row "refresh"))))
                   (id (mrjam-oidc:verifier-id-token (j tokens "id_token") (mrjam-oidc:lire-jwks client)
                         :client-id (mrjam-oidc::client-oidc-id client) :maintenant maintenant :nonce (champ row "nonce")
                         :access-token (j tokens "access_token"))))
              (unless (equal (champ row "subject") (mrjam-oidc:identite-sujet id)) (refuser))
              (base c (lambda (db) (mrjam-native:sqlite-requete db
                "UPDATE log_sessions SET access=?,refresh=? WHERE digest=?"
                (list (j tokens "access_token") (j tokens "refresh_token") (champ row "digest")))))
              (setf r (mrjam-oidc:introspecter-jeton client (j tokens "access_token"))
                    d (mrjam-oidc:reponse-oidc-document r))))
          (unless (and (= 200 (mrjam-oidc:reponse-oidc-statut r)) (eq :true (j d "active")))
            (base c (lambda (db) (mrjam-native:sqlite-requete db "DELETE FROM log_sessions WHERE digest=?" (list (champ row "digest")))))
            (return-from session-digest nil))
          (base c (lambda (db) (mrjam-native:sqlite-requete db "UPDATE log_sessions SET seen=? WHERE digest=?" (list maintenant (champ row "digest")))))
          ;; Ne jamais retourner les jetons fournisseur à la couche HTTP.
          (list (cons "username" (champ row "username")) (cons "csrf" (champ row "csrf"))
                (cons "expiresAt" (champ row "expires")) (cons "createdAt" (champ row "created"))
                (cons "subject" (champ row "subject"))
                (cons "auth_time" (champ row "auth_time")) (cons "compte" p)))))))

(defun politique (c subject)
  (base c (lambda (db) (first (mrjam-native:sqlite-requete db
     "SELECT * FROM log_principaux WHERE subject=?" (list subject))))))
(defun enregistrer-principal (c subject mail)
  "Admission vérifiée, identité native explicite ; aucune fusion par mail."
  (unless (and (mrjam-oidc::texte-borne-p subject 36 36) (stringp mail)) (refuser 400))
  (principal c (mrjam-oidc:issuer-client "mrjam-vision") subject)
  (base c (lambda (db) (mrjam-native:sqlite-requete db
    "INSERT INTO log_principaux(subject,mail,duration,minimum,qualified_after) VALUES(?,?,604800,'any',?)
     ON CONFLICT(subject) DO UPDATE SET mail=excluded.mail"
    (list subject (string-downcase mail) (temps))))) t)
(defun duree-session (c subject)
  (or (champ (politique c subject) "duration") 604800))
(defun verification-renforcee-p (c session &optional (maintenant (temps)))
  "Pas de claim amr inventé : seulement un sujet neuf dont l'enrôlement MFA
obligatoire a été configuré/qualifié par l'opérateur, et une authentification
signée postérieure à ce point. La fraîcheur expire sans bloquer le métier."
  (let* ((p (and session (politique c (champ session "subject"))))
         (auth (champ session "auth_time")))
    (and (equal (champ p "minimum") "mfa") (integerp auth)
         (<= (champ p "qualified_after") auth maintenant) (< (- maintenant auth) 900))))

(defun csrf-valide-p (session origine hote csrf)
  (and session (equal origine (concatenate 'string "https://" hote))
       (stringp csrf) (mrjam-native:secret-egal-p csrf (champ session "csrf"))))
(defun deconnecter (c hote cookies)
  (client c hote)
  (let ((token (token-cookie cookies "__Host-mrj_session")))
    (when token (sb-thread:with-mutex ((contexte-verrou c))
      ;; Suppression locale d'abord : même une panne IdP n'annule pas le logout.
      (let ((refresh (base c (lambda (db) (mrjam-native:sqlite-transaction db (lambda (db)
          (let ((r (first (mrjam-native:sqlite-requete db "SELECT refresh FROM log_sessions WHERE digest=? AND host=?" (list (mrjam-native:sha256 token) hote)))))
            (mrjam-native:sqlite-requete db "DELETE FROM log_sessions WHERE digest=? AND host=?" (list (mrjam-native:sha256 token) hote))
            (champ r "refresh"))))))))
        (when refresh (mrjam-oidc:revoquer-jeton (client c hote) refresh :type "refresh_token"))))))
  (cookie-session "" 0))

(defun revoquer-autres (c hote cookies)
  (let ((s (session c hote cookies)) (token (token-cookie cookies "__Host-mrj_session")))
    (unless s (refuser))
    (base c (lambda (db) (mrjam-native:sqlite-requete db
        "DELETE FROM log_sessions WHERE username=? AND digest<>?"
        (list (champ s "username") (mrjam-native:sha256 token))))))
  t)
