(defpackage #:mrjam-oidc-kanidm-tests (:use #:cl) (:export #:verifier))
(in-package #:mrjam-oidc-kanidm-tests)

(defun verifier (chemin)
  "Vrai IdP synthétique en cours d'exécution ; aucun credential opérateur transmis."
  (let* ((p (vision:parse-json (uiop:read-file-string chemin)))
         (client (mrjam-oidc:faire-client-oidc "mrjam-vision"
                   (vision:json-object-get p "secret") (vision:json-object-get p "curl")
                   :ca (vision:json-object-get p "ca") :port (vision:json-object-get p "port")
                   :hotes '("vision.mrj.am")))
         (discovery (mrjam-oidc:lire-discovery client))
         (jwks (mrjam-oidc:lire-jwks client))
         (reponse (mrjam-oidc:echanger-code client (vision:json-object-get p "code")
                     (vision:json-object-get p "verifier") "vision.mrj.am"))
         (document (mrjam-oidc:reponse-oidc-document reponse))
         (nombre 0))
    ;; Avant toute vérification supplémentaire : conserver l'effet de l'échange.
    ;; Le fichier est créé0600 par la fixture, sous répertoire0700 ; pas de log.
    (with-open-file (out (vision:json-object-get p "reponse") :direction :output
                        :if-exists :overwrite :if-does-not-exist :error :external-format :utf-8)
      (write-string (vision:json-encode document) out))
    (labels ((valide (condition) (assert condition) (incf nombre)))
      (valide (= 200 (mrjam-oidc:reponse-oidc-statut reponse)))
      (valide (mrjam-oidc:verifier-discovery discovery "mrjam-vision"))
      (let ((id (mrjam-oidc:verifier-id-token (vision:json-object-get document "id_token") jwks
                  :client-id "mrjam-vision" :nonce (vision:json-object-get p "nonce")
                  :maintenant (vision:json-object-get p "maintenant")
                  :access-token (vision:json-object-get document "access_token"))))
        (valide (equal (mrjam-oidc:identite-sujet id) (vision:json-object-get p "uuid")))
        (valide (equal (mrjam-oidc:identite-issuer id) (mrjam-oidc:issuer-client "mrjam-vision")))
        (valide (not (search (vision:json-object-get document "id_token") (prin1-to-string id)))))
      (let* ((introspection (mrjam-oidc:introspecter-jeton client (vision:json-object-get document "access_token")))
             (donnees (mrjam-oidc:reponse-oidc-document introspection)))
        (valide (= 200 (mrjam-oidc:reponse-oidc-statut introspection)))
        (valide (eq :true (vision:json-object-get donnees "active")))
        (valide (equal (vision:json-object-get donnees "sub") (vision:json-object-get p "uuid"))))
      (let* ((renouvellement (mrjam-oidc:renouveler-jetons client (vision:json-object-get document "refresh_token")))
             (nouveaux (mrjam-oidc:reponse-oidc-document renouvellement)))
        (valide (= 200 (mrjam-oidc:reponse-oidc-statut renouvellement)))
        (valide (stringp (vision:json-object-get nouveaux "access_token")))
        ;; Vérifier indépendamment le nouveau JWT ; aucun retour déduit du seul200.
        (let ((id (mrjam-oidc:verifier-id-token (vision:json-object-get nouveaux "id_token") jwks
                    :client-id "mrjam-vision" :nonce (vision:json-object-get p "nonce")
                    :maintenant (vision:json-object-get p "maintenant")
                    :access-token (vision:json-object-get nouveaux "access_token"))))
          (valide (equal (mrjam-oidc:identite-sujet id) (vision:json-object-get p "uuid"))))
        (valide (= 200 (mrjam-oidc:reponse-oidc-statut
                        (mrjam-oidc:revoquer-jeton client (vision:json-object-get nouveaux "refresh_token")))))
        (let* ((apres (mrjam-oidc:introspecter-jeton client (vision:json-object-get nouveaux "access_token")))
               (donnees (mrjam-oidc:reponse-oidc-document apres)))
          (valide (= 200 (mrjam-oidc:reponse-oidc-statut apres)))
          (valide (eq :false (vision:json-object-get donnees "active"))))
        (valide (= 400 (mrjam-oidc:reponse-oidc-statut
                        (mrjam-oidc:renouveler-jetons client (vision:json-object-get nouveaux "refresh_token"))))))
      (format t "~&OIDC Kanidm réel : ~D assertions terminées.~%" nombre)
      nombre)))
