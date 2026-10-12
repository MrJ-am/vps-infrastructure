(in-package #:mrjam-oidc)

(defstruct (demarrage (:constructor %demarrage)) state binding nonce challenge expiration)
(defmethod print-object ((objet demarrage) stream)
  (print-unreadable-object (objet stream :type t)
    (write-string "paramètres sensibles masqués" stream)))

(defun secret-url-p (valeur)
  (and (stringp valeur) (= (length valeur) 43)
       (every (lambda (c) (or (char<= #\a c #\z) (char<= #\A c #\Z)
                             (char<= #\0 c #\9) (find c "_-"))) valeur)))

(defun hote-applicatif-p (hote)
  (and (stringp hote) (<= 1 (length hote) 253)
       (uiop:string-suffix-p hote ".mrj.am")
       (every (lambda (c) (or (char<= #\a c #\z) (char<= #\0 c #\9)
                             (find c ".-"))) hote)
       (not (search ".." hote)) (not (char= #\. (char hote 0)))))

(defun retour-applicatif-p (retour)
  (and (texte-borne-p retour 1 4096)
       (not (find (code-char 127) retour))
       (or (member retour '("/" "/auth/mcp" "/#administration" "/#compte") :test #'equal)
           (uiop:string-prefix-p "/oauth/authorize?" retour))))

(defun initialiser-transactions (chemin)
  "Table additive propre au client Kanidm ; aucune modification de données métier.
L'appel appartient au démarrage explicite, jamais à LOAD-SYSTEM."
  (mrjam-native:avec-sqlite chemin
    (lambda (db)
      (mrjam-native:sqlite-requete db
        "CREATE TABLE IF NOT EXISTS log_transactions (
         state TEXT PRIMARY KEY, binding TEXT NOT NULL, client_id TEXT NOT NULL,
         host TEXT NOT NULL, verifier TEXT NOT NULL, nonce TEXT NOT NULL,
         retour TEXT NOT NULL, expires INTEGER NOT NULL, stepup INTEGER NOT NULL
         CHECK(stepup IN (0,1)), invitation TEXT, notice TEXT)"))))

(defun demarrer-transaction (chemin client-id hote maintenant
                            &key (retour "/") stepup invitation notice)
  "Le serveur fournit client/hôte depuis sa configuration vérifiée.
Seuls challenge S256/state/nonce sont destinés à l'URL ; binding au cookie HttpOnly.
Le verifier reste dans SQLite. Le secret client IdP ne figure jamais dans cette table."
  (unless (and (identifiant-client-p client-id) (hote-applicatif-p hote)
               (integerp maintenant) (<= 0 maintenant #x1fffffffffffff)
               (retour-applicatif-p retour) (member stepup '(nil t))
               (or (null invitation) (secret-url-p invitation))
               (or (null notice) (texte-borne-p notice 1 128))
               (eq (null invitation) (null notice)))
    (refuser :transaction-parametres))
  (let* ((state (mrjam-native:aleatoire-url)) (binding (mrjam-native:aleatoire-url))
         (verifier (mrjam-native:aleatoire-url)) (nonce (mrjam-native:aleatoire-url))
         (expiration (+ maintenant 600)))
    (mrjam-native:avec-sqlite chemin
      (lambda (db)
        (mrjam-native:sqlite-transaction db
          (lambda (db)
            (mrjam-native:sqlite-requete db "DELETE FROM log_transactions WHERE expires<=?" (list maintenant))
            ;; Une arrivée anonyme ne peut faire croître cet état sans borne.
            (when (>= (cdr (assoc "nombre" (first (mrjam-native:sqlite-requete db
                                        "SELECT count(*) AS nombre FROM log_transactions")) :test #'equal)) 4096)
              (refuser :capacite-transactions))
            (mrjam-native:sqlite-requete db "INSERT INTO log_transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)"
              (list (mrjam-native:sha256 state) (mrjam-native:sha256 binding) client-id hote verifier nonce
                    retour expiration (if stepup 1 0) invitation notice))))))
    (%demarrage :state state :binding binding :nonce nonce :expiration expiration
                :challenge (mrjam-native:base64
                             (mrjam-native::digest-octets (mrjam-native::octets verifier))
                             :url t :sans-remplissage t))))

(defun consommer-transaction (chemin state binding client-id hote maintenant)
  "Consommation atomique avant échange du code, y compris entre processus.
L'échange HTTP s'effectue après COMMIT, pas sous le verrou SQL. Un échec/timeout
ne remet pas la transaction en circulation : créer un nouveau parcours de connexion."
  (unless (and (secret-url-p state) (secret-url-p binding)
               (identifiant-client-p client-id) (hote-applicatif-p hote)
               (integerp maintenant) (<= 0 maintenant #x1fffffffffffff))
    (refuser :transaction-parametres))
  (mrjam-native:avec-sqlite chemin
    (lambda (db)
      (mrjam-native:sqlite-transaction db
        (lambda (db)
          (let* ((empreinte (mrjam-native:sha256 state))
                 (ligne (first (mrjam-native:sqlite-requete db
                                  "SELECT * FROM log_transactions WHERE state=?" (list empreinte)))))
            (flet ((champ (nom) (cdr (assoc nom ligne :test #'equal))))
              (unless (and ligne (equal client-id (champ "client_id")) (equal hote (champ "host"))
                           (> (champ "expires") maintenant)
                           (mrjam-native:secret-egal-p (mrjam-native:sha256 binding) (champ "binding")))
                (refuser :transaction-invalide))
              (mrjam-native:sqlite-requete db "DELETE FROM log_transactions WHERE state=?" (list empreinte))
              ;; Ne pas exposer ce résultat aux réponses navigateur ou journaux.
              ligne)))))))
