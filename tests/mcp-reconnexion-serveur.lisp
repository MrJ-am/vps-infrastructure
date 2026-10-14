;;; Image de test propre, socket Unix privé et fournisseur OIDC de fixture.
;;; Aucun remplacement de fonction d'authentification ou de transport produit.
(require :asdf)
(load (or (uiop:getenv "MRJAM_CHARGEUR_TESTS")
          (merge-pathnames "../assemblage/charger.lisp" *load-truename*)))
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") (error "Libcrypto requis.")))
(mrjam-native:initialiser-sqlite (or (uiop:getenv "MRJAM_LIBSQLITE") (error "SQLite requis.")))

(let* ((fichier (or (uiop:getenv "MRJAM_RECONNEXION_FIXTURE") (error "Fixture requise.")))
       (d (vision:parse-json (uiop:read-file-string fichier)))
       (client (mrjam-oidc:faire-client-oidc "mrjam-vision" "secret-oidc-synthetique"
                 (vision:json-object-get d "curl") :ca (vision:json-object-get d "ca")
                 :port (vision:json-object-get d "port") :hotes '("vision.mrj.am")))
       (contexte (mrjam-log::initialiser-oauth (mrjam-log:initialiser
         (mrjam-log:faire-contexte (vision:json-object-get d "base")
           (list (cons "vision.mrj.am" client))
           (lambda (issuer subject)
             (assert (equal issuer (mrjam-oidc:issuer-client "mrjam-vision")))
             (let* ((actifs (vision:parse-json (uiop:read-file-string fichier)))
                    (nom (cond ((equal subject "00000000-0000-4000-8000-000000000001") "alice")
                               ((equal subject "00000000-0000-4000-8000-000000000002") "bob"))))
               (vision:jobject "actif" (if (and nom (not (eq :false (vision:json-object-get actifs nom)))) :true :false)
                               "utilisateur" (or nom "inconnu") "administrateur" :false))))))))
  (mrjam-metier::servir (mrjam-metier:faire-configuration
    :log contexte :socket (vision:json-object-get d "socket")
    :document-vision (vision:json-object-get d "vision")
    :executeur-vision (lambda (&rest args) (declare (ignore args))
                       (error "Aucune donnée pédagogique dans cette qualification OAuth.")))))
