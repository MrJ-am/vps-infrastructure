(in-package #:mrjam-metier)

(defun obligatoire (nom)
  (or (uiop:getenv nom) (error "Configuration requise : ~A" nom)))

(defun secret-fichier (nom)
  (let ((path (uiop:getenv nom)))
    (when path (string-trim '(#\Space #\Tab #\Newline #\Return)
                           (sb-ext:octets-to-string (mrjam-courriel::lire-octets-prives path 128) :external-format :utf-8)))))

(defun configurer-cycle (&optional log)
  (when (uiop:getenv "VISION_CYCLE_DSN")
    (mrjam-native:initialiser-sqlite (obligatoire "MRJAM_LIBSQLITE"))
    (let ((client (unless log (mrjam-identite:faire-client "mrjam-cycle"
                    (mrjam-courriel:lire-secret-prive (obligatoire "VISION_CYCLE_CLIENT_SECRET")) (obligatoire "MRJAM_CURL")))))
      (vision-cycle:faire-cycle (obligatoire "VISION_CYCLE_DSN") (obligatoire "VISION_CYCLE_ETAT")
        (mrjam-courriel:lire-prive (obligatoire "MRJ_SMTP_SECRET")) (mrjam-courriel:lire-prive (obligatoire "VISION_CYCLE_CONFIG"))
        (lambda (d)
          (if log
              (progn
                (unless (equal (vision:json-object-get d "emetteur") (mrjam-oidc:issuer-client "mrjam-vision"))
                  (mrjam-log::refuser 403))
                ;; Le mail a été vérifié lors de l'invitation privée ; aucune
                ;; lecture/credential maître IdP nécessaire aux rappels Vision.
                (mrjam-courriel:adresse (mrjam-log::champ
                  (mrjam-log::politique log (vision:json-object-get d "sujet")) "mail")))
              (mrjam-identite:adresse-verifiee client d))) (obligatoire "AGE")))))

(defun client-identite (nom variable)
  (mrjam-identite:faire-client nom (mrjam-courriel:lire-secret-prive (obligatoire variable)) (obligatoire "MRJAM_CURL")))

(defun configurer-log ()
  (when (uiop:getenv "MRJ_LOG_DATABASE")
    (mrjam-native:initialiser-sqlite (obligatoire "MRJAM_LIBSQLITE"))
    (let* ((id "mrjam-vision")
           (dsn (obligatoire "MRJ_LOG_IDENTITES_DSN"))
           (client (mrjam-oidc:faire-client-oidc id
               ;; Secret natif Kanidm : ne pas lui imposer le format43 des
               ;; anciens clients Keycloak. Le client valide sa propre borne.
               (string-trim '(#\Newline #\Return)
                 (sb-ext:octets-to-string
                   (mrjam-courriel::lire-octets-prives (obligatoire "MRJ_LOG_CLIENT_SECRET") 512)
                   :external-format :utf-8))
               (obligatoire "MRJAM_CURL") :ca (obligatoire "MRJAM_CA_FILE")
               :hotes '("vision.mrj.am"))))
      (mrjam-log::initialiser-oauth (mrjam-log:initialiser (mrjam-log:faire-contexte (obligatoire "MRJ_LOG_DATABASE")
        (list (cons "vision.mrj.am" client))
        (lambda (issuer subject)
          (mrjam-native:avec-connexion dsn (lambda (c)
            (let ((r (first (mrjam-native:requete c
                             "SELECT vision_gestion.identifier($1,$2)::text AS compte" (list issuer subject)))))
              (vision:parse-json (cdr (assoc "compte" r :test #'equal)))))))))))))
(defun configurer-admission ()
  (when (uiop:getenv "MRJ_ADMISSION_DSN")
    (mrjam-native:initialiser-sqlite (obligatoire "MRJAM_LIBSQLITE"))
    (vision-admission:faire-admission (obligatoire "MRJ_ADMISSION_DSN") (obligatoire "MRJ_ADMISSION_ETAT")
      (mrjam-courriel:lire-prive (obligatoire "MRJ_SMTP_SECRET")) (client-identite "mrjam-admission" "MRJ_ADMISSION_SECRET"))))
(defun configurer-fermeture (admission)
  (when (uiop:getenv "MRJ_FERMETURE_DSN")
    (list :secret (mrjam-courriel:lire-secret-prive (obligatoire "MRJ_FERMETURE_HOOK"))
          :contexte (vision-fermeture:faire-fermeture (obligatoire "MRJ_FERMETURE_DSN") (obligatoire "MRJ_FERMETURE_ETAT")
                      (mrjam-courriel:lire-prive (obligatoire "MRJ_SMTP_SECRET")) (mrjam-courriel:lire-prive (obligatoire "MRJ_FERMETURE_CONFIG"))
                      (client-identite "mrjam-fermeture" "MRJ_FERMETURE_CLIENT") admission (obligatoire "AGE")))))

(defun periodique (secondes fonction)
  (let ((prochaine 0))
    (lambda () (when (<= prochaine (get-universal-time))
                 (funcall fonction) (setf prochaine (+ (get-universal-time) secondes))))))
(defun tache-courriel ()
  (when (uiop:getenv "MRJ_COURRIEL_FILE")
    (mrjam-native:initialiser-sqlite (obligatoire "MRJAM_LIBSQLITE"))
    (let* ((smtp (mrjam-courriel:verifier-smtp (mrjam-courriel:lire-prive (obligatoire "MRJ_SMTP_SECRET"))))
           (file (mrjam-courriel:faire-file (obligatoire "MRJ_COURRIEL_FILE") (vision:json-object-get smtp "from_address"))))
      (cons "courriel" (lambda () (mrjam-courriel:traiter file smtp) (mrjam-courriel:purger file))))))
(defun tache-entretien ()
  (when (uiop:getenv "VISION_ENTRETIEN_DSN")
    (let ((dsn (obligatoire "VISION_ENTRETIEN_DSN")))
      (cons "purge-vision" (periodique 86400 (lambda ()
        (mrjam-native:avec-connexion dsn (lambda (c) (mrjam-native:transaction c (lambda (c)
          (mrjam-native:requete c "SELECT vision_gestion.purger(),vision_gestion.purger_admissions()")))))))))))

(defun main ()
  (handler-case
      (progn
        ;; Cette fonction est la seule entrée de l'exécutable propre : les DSO,
        ;; connexions et secrets n'existent jamais dans l'image de construction.
        (mrjam-native:initialiser-crypto (obligatoire "MRJAM_LIBCRYPTO"))
        (mrjam-native:initialiser-postgresql (obligatoire "MRJAM_LIBPQ"))
        (sb-sys:enable-interrupt sb-posix:sigterm
          (lambda (&rest ignores) (declare (ignore ignores)) (sb-ext:exit :code 0 :abort nil)))
        (let* ((log (configurer-log)) (cycle (configurer-cycle log))
               (admission (configurer-admission)) (fermeture (configurer-fermeture admission)))
          (servir (faire-configuration
                  :matheval (matheval:faire-contexte :connexion (obligatoire "MATHEVAL_DSN")
                              :version (obligatoire "MATHEVAL_BANK_VERSION") :activation (secret-fichier "MATHEVAL_SETUP_HASH_FILE"))
                  :origine (obligatoire "MATHEVAL_ORIGIN")
                  :document-vision (obligatoire "VISION_DOCUMENT_ROOT")
                  :executeur-vision (executeur-vision (obligatoire "VISION_DSN"))
                  :gestion-dsn (uiop:getenv "VISION_GESTION_DSN")
                  :log log
                  :cycle cycle :admission admission :fermeture fermeture
                  :taches (append (when cycle (list (cons "cycle-vision" (lambda () (vision-cycle:traiter cycle)))))
                                  (when admission (list (cons "admission" (lambda () (vision-admission:traiter admission)))))
                                  (when fermeture (list (cons "fermeture" (lambda () (vision-fermeture:traiter (getf fermeture :contexte))))))
                                  (let ((f (tache-courriel))) (when f (list f)))
                                  (let ((f (tache-entretien))) (when f (list f))))
                  :socket (obligatoire "MRJAM_SOCKET")))))
    (error ()
      ;; Ni formulaire, ni conditions contenant paramètres/chemins secrets.
      (format *error-output* "Démarrage métier refusé : configuration ou dépendance indisponible.~%")
      (finish-output *error-output*) (sb-ext:exit :code 1))))
