(in-package #:mrjam-oidc)

(defstruct (client-oidc (:constructor %client-oidc)) id secret curl ca port hotes)
(defstruct reponse-oidc statut document)
(defmethod print-object ((objet client-oidc) stream)
  (print-unreadable-object (objet stream :type t)
    (write-string "configuration sensible masquée" stream)))
(defmethod print-object ((objet reponse-oidc) stream)
  (print-unreadable-object (objet stream :type t)
    (format stream "statut ~D, contenu masqué" (reponse-oidc-statut objet))))

(defun fichier-transport-p (chemin)
  (and (or (stringp chemin) (pathnamep chemin))
       (uiop:absolute-pathname-p chemin) (probe-file chemin)
       (not (uiop:directory-pathname-p chemin))
       (texte-borne-p (namestring (pathname chemin)) 1 4096)
       (not (find (code-char 127) (namestring (pathname chemin))))))

(defun faire-client-oidc (id secret curl &key ca (port 8443) hotes)
  "Endpoint HTTPS log.mrj.am, raccordé uniquement au Kanidm loopback configuré.
CA/secret/exécutable acquis au démarrage ; aucun socket, migration ou secret IdP
administrateur ici. PORT change la connexion locale, jamais l'issuer ni le SNI."
  (unless (and (identifiant-client-p id) (texte-borne-p secret 16 256)
               (every (lambda (c) (<= 33 (char-code c) 126)) secret)
               (fichier-transport-p curl) (or (null ca) (fichier-transport-p ca))
               (integerp port) (<= 1 port 65535)
               (listp hotes) (<= 1 (length hotes) 8) (every #'hote-applicatif-p hotes)
               (= (length hotes) (length (remove-duplicates hotes :test #'equal))))
    (refuser :configuration-transport))
  (%client-oidc :id id :secret secret :curl (namestring (pathname curl))
                :ca (when ca (namestring (pathname ca))) :port port :hotes (copy-list hotes)))

(defun formulaire-oidc (parametres)
  (let ((texte
          (format nil "~{~A~^&~}"
            (mapcar (lambda (entree)
                      (unless (and (consp entree) (stringp (car entree)) (stringp (cdr entree)))
                        (refuser :formulaire))
                      (concatenate 'string (mrjam-native:parametre-url (car entree)) "="
                                          (mrjam-native:parametre-url (cdr entree)))) parametres))))
    (unless (<= (length texte) 32768) (refuser :formulaire)) texte))

(defun chemin-oidc-p (client chemin)
  (member chemin
    (list (concatenate 'string "/oauth2/openid/" (client-oidc-id client) "/.well-known/openid-configuration")
          (concatenate 'string "/oauth2/openid/" (client-oidc-id client) "/public_key.jwk")
          "/oauth2/token" "/oauth2/token/introspect" "/oauth2/token/revoke")
    :test #'equal))

(defun %requete-oidc (client chemin parametres)
  (unless (and (typep client 'client-oidc) (chemin-oidc-p client chemin))
    (refuser :endpoint-transport))
  (let ((processus nil)
        (config
          (with-output-to-string (sortie)
            ;; Aucun proxy, HTTP en clair, redirection ou rc implicite. La cible
            ;; réseau est strictement 127.0.0.1 ; le certificat doit nommer Log.
            (format sortie "silent~%show-error~%max-time = 10~%connect-timeout = 5~%max-filesize = 65536~%proxy = \"\"~%noproxy = \"*\"~%proto = \"=https\"~%tlsv1.2~%")
            (flet ((option (nom valeur)
                     (format sortie "~A = ~A~%" nom (mrjam-native:chaine-config-curl valeur))))
              (option "url" (concatenate 'string "https://log.mrj.am" chemin))
              (option "connect-to" (format nil "log.mrj.am:443:127.0.0.1:~D" (client-oidc-port client)))
              (when (client-oidc-ca client) (option "cacert" (client-oidc-ca client)))
              (option "header" "Accept: application/json")
              (option "header" "Expect:")
              (when parametres
                (option "request" "POST")
                (option "header" "Content-Type: application/x-www-form-urlencoded")
                ;; Kanidm authentifie /token par Basic. Introspection/révocation
                ;; reçoivent le jeton opaque, sans secret client (métadonnées none).
                (when (equal chemin "/oauth2/token")
                  ;; Le secret n'apparaît ni dans argv, ni dans un fichier/artefact.
                  (option "header"
                    (concatenate 'string "Authorization: Basic "
                      (mrjam-native:base64
                        (sb-ext:string-to-octets
                          (concatenate 'string (mrjam-native:parametre-url (client-oidc-id client)) ":"
                                              (mrjam-native:parametre-url (client-oidc-secret client)))
                          :external-format :utf-8)))))
                (option "data" (formulaire-oidc parametres)))
              ;; Le statut n'est pas extrait d'un préambule HTTP/proxy ambigu.
              (format sortie "write-out = \"\\n%{response_code}\"~%")))))
    (unwind-protect
      (sb-ext:with-timeout 15
        (setf processus (sb-ext:run-program (client-oidc-curl client) '("--disable" "--config" "-")
                           :input :stream :output :stream :error nil :wait nil :external-format :utf-8))
        (write-string config (sb-ext:process-input processus))
        (finish-output (sb-ext:process-input processus))
        (close (sb-ext:process-input processus))
        (let* ((tampon (make-array 65541 :element-type 'character))
               (nombre (read-sequence tampon (sb-ext:process-output processus))))
          (unless (and (<= 4 nombre) (< nombre (length tampon))
                       (char= #\Newline (aref tampon (- nombre 4)))
                       (every (lambda (c) (char<= #\0 c #\9)) (subseq tampon (- nombre 3) nombre)))
            (refuser :reponse-transport))
          (sb-ext:process-wait processus)
          (unless (eql 0 (sb-ext:process-exit-code processus)) (refuser :transport))
          (let* ((statut (parse-integer tampon :start (- nombre 3) :end nombre))
                 (document (when (> nombre 4)
                             (objet-json-borne
                               (sb-ext:string-to-octets (subseq tampon 0 (- nombre 4)) :external-format :utf-8)))))
            (when (<= 300 statut 399) (refuser :redirection-transport))
            (unless (<= 200 statut 599) (refuser :reponse-transport))
            (make-reponse-oidc :statut statut :document document))))
      (when processus
        (when (sb-ext:process-alive-p processus) (sb-ext:process-kill processus sb-posix:sigkill))
        (sb-ext:process-close processus)))))

(defun requete-oidc (client chemin &optional parametres)
  ;; Une erreur lib/OS ne doit pas exposer la réponse, une URL ou un secret.
  ;; Un timeout ne déclenche aucune répétition automatique d'un POST.
  (handler-case (%requete-oidc client chemin parametres)
    (oidc-error (condition) (error condition))
    (error () (refuser :transport))))

(defun lire-discovery (client)
  (let ((reponse (requete-oidc client
                  (concatenate 'string "/oauth2/openid/" (client-oidc-id client) "/.well-known/openid-configuration"))))
    (unless (= 200 (reponse-oidc-statut reponse)) (refuser :discovery-transport))
    (verifier-discovery (reponse-oidc-document reponse) (client-oidc-id client))
    (reponse-oidc-document reponse)))

(defun lire-jwks (client)
  (let ((reponse (requete-oidc client
                  (concatenate 'string "/oauth2/openid/" (client-oidc-id client) "/public_key.jwk"))))
    (unless (and (= 200 (reponse-oidc-statut reponse)) (vision:json-object-p (reponse-oidc-document reponse)))
      (refuser :jwks-transport))
    (reponse-oidc-document reponse)))

(defun echanger-code (client code verifier hote)
  (unless (and (typep client 'client-oidc) (texte-borne-p code 1 8192) (secret-url-p verifier)
               (member hote (client-oidc-hotes client) :test #'equal))
    (refuser :echange-parametres))
  (requete-oidc client "/oauth2/token"
    (list (cons "grant_type" "authorization_code") (cons "code" code)
          (cons "code_verifier" verifier) (cons "redirect_uri" (concatenate 'string "https://" hote "/auth/retour")))))

(defun operation-jeton (client endpoint jeton type &optional actualiser)
  (unless (and (texte-borne-p jeton 1 16384)
               (member type '("access_token" "refresh_token") :test #'equal))
    (refuser :jeton-parametres))
  (requete-oidc client endpoint
    (if actualiser (list (cons "grant_type" "refresh_token") (cons "refresh_token" jeton))
        (list (cons "token" jeton) (cons "token_type_hint" type)))))

(defun introspecter-jeton (client jeton &key (type "access_token"))
  (operation-jeton client "/oauth2/token/introspect" jeton type))
(defun revoquer-jeton (client jeton &key (type "refresh_token"))
  (operation-jeton client "/oauth2/token/revoke" jeton type))
(defun renouveler-jetons (client jeton)
  (operation-jeton client "/oauth2/token" jeton "refresh_token" t))
