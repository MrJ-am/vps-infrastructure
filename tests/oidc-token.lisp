(defpackage #:mrjam-oidc-tests (:use #:cl) (:export #:verifier))
(in-package #:mrjam-oidc-tests)

(defun verifier ()
  (let* ((fixture (vision:parse-json
                    (uiop:read-file-string
                      (asdf:system-relative-pathname "mrjam-oidc" "tests/fixtures/oidc-es256.json"))))
         (jwks (vision:json-object-get fixture "jwks"))
         (parametres (vision:json-object-get fixture "parametres"))
         (client (vision:json-object-get parametres "client-id"))
         (nonce (vision:json-object-get parametres "nonce"))
         (maintenant (vision:json-object-get parametres "maintenant"))
         (valide nil) (nombre 0))
    (labels ((tester (token attendu &optional (cles jwks) options)
               (incf nombre)
               (let ((resultat (handler-case
                                  (mrjam-oidc:verifier-id-token token cles :client-id client :nonce nonce
                                    :maintenant maintenant :tolerance 0
                                    :max-age (vision:json-object-get options "max-age")
                                    :access-token (vision:json-object-get options "access-token"))
                                (mrjam-oidc:oidc-error () nil))))
                 (assert (eq (not (null resultat)) attendu))
                 (when resultat
                   (assert (equal (mrjam-oidc:identite-issuer resultat) (mrjam-oidc:issuer-client client)))
                   (assert (equal (mrjam-oidc:identite-sujet resultat)
                                  (vision:json-object-get (mrjam-oidc:identite-claims resultat) "sub"))))
                 resultat)))
      ;; Fixture des endpoints/profils issus du code officiel1.11.2 ; échange réel séparé.
      (let ((discovery (vision:jobject
                        "issuer" (mrjam-oidc:issuer-client client)
                        "authorization_endpoint" "https://log.mrj.am/ui/oauth2"
                        "token_endpoint" "https://log.mrj.am/oauth2/token"
                        "jwks_uri" (concatenate 'string (mrjam-oidc:issuer-client client) "/public_key.jwk")
                        "response_types_supported" (vision:jarray "code")
                        "id_token_signing_alg_values_supported" (vision:jarray "ES256")
                        "code_challenge_methods_supported" (vision:jarray "S256")
                        "token_endpoint_auth_methods_supported" (vision:jarray "client_secret_basic"))))
        (assert (mrjam-oidc:verifier-discovery discovery client)) (incf nombre)
        (dolist (entry (vision:json-object-entries discovery))
          (let ((copie (vision:parse-json (mrjam-native:json-js discovery))))
            (setf (cdr (assoc (car entry) (vision:json-object-entries copie) :test #'equal))
                  (if (vision:json-array-p (cdr entry)) (vision:jarray "non-supporte")
                      "https://intrus.invalid"))
            (assert (handler-case (progn (mrjam-oidc:verifier-discovery copie client) nil)
                      (mrjam-oidc:oidc-error () t))) (incf nombre))))
      (dolist (cas (vision:json-array-items (vision:json-object-get fixture "cas")))
        (let* ((nom (vision:json-object-get cas "nom")) (token (vision:json-object-get cas "token"))
               (resultat (tester token (eq :true (vision:json-object-get cas "accepte")) jwks
                                (vision:json-object-get cas "options"))))
          (when (equal nom "valide") (setf valide token))
          (when resultat (assert (> (mrjam-oidc:identite-expiration resultat) maintenant)))))
      (assert valide)
      ;; Mutation de chaque octet signé sans nouvelle signature ; JSON ou signature doivent échouer.
      (loop for i below (length valide) do
        (unless (char= #\. (char valide i))
          (let ((copie (copy-seq valide)))
            (setf (char copie i) (if (char= #\A (char copie i)) #\B #\A))
            (tester copie nil))))
      (dolist (token '("" "a" "a.b" "a.b.c.d" "=.=.=" "a .b.c")) (tester token nil))
      (tester (make-string 16385 :initial-element #\A) nil)
      (let ((parties (uiop:split-string valide :separator ".")))
        (dolist (signature '("" "AA" "AA==" "AA+AA" "AA/AA" "AA AA"))
          (tester (format nil "~A.~A.~A" (first parties) (second parties) signature) nil))
        (tester (format nil "~A.~A.~A" (first parties) (second parties)
                        (mrjam-native:base64 (make-array 64 :element-type '(unsigned-byte 8)
                                                        :initial-element 0) :url t :sans-remplissage t)) nil))
      (let ((cle (first (vision:json-array-items (vision:json-object-get jwks "keys")))))
        (tester valide nil (vision:jobject "keys" (vision:jarray cle cle)))
        (tester valide nil (vision:jobject "keys" (vision:jarray)))
        (dolist (modification '(("crv" . "P-384") ("kty" . "RSA") ("use" . "enc")
                                ("alg" . "HS256") ("d" . "prive-injecte")
                                ("x" . "AA") ("y" . "AA")))
          (let ((copie (vision:parse-json (mrjam-native:json-js cle))))
            (let ((pair (assoc (car modification) (vision:json-object-entries copie) :test #'equal)))
              (if pair (setf (cdr pair) (cdr modification))
                  (push (copy-tree modification) (vision:json-object-entries copie))))
            (tester valide nil (vision:jobject "keys" (vision:jarray copie)))))
        ;; Coordonnées nulles et hors domaine avant vérification optimisée.
        (dolist (coordonnee '(0 255))
          (let ((xy (mrjam-native:base64 (make-array 32 :element-type '(unsigned-byte 8)
                                                     :initial-element coordonnee)
                                       :url t :sans-remplissage t)))
            (tester valide nil (vision:jobject "keys" (vision:jarray
              (vision:jobject "kid" "cle-fixture" "kty" "EC" "crv" "P-256" "x" xy "y" xy)))))))
      ;; Non-canonicalité des bits de remplissage du dernier sextet.
      (assert (handler-case (progn (mrjam-oidc::decoder-url "AB" 16) nil)
                (mrjam-oidc:oidc-error () t)))
      (incf nombre)
      ;; Aucune identité de requête dans un global ; lectures concurrentes indépendantes.
      (let ((resultats (make-array 8 :initial-element nil)) (threads '())
            (personnes (remove-if-not
                         (lambda (cas) (uiop:string-prefix-p "personne-" (vision:json-object-get cas "nom")))
                         (vision:json-array-items (vision:json-object-get fixture "cas")))))
        (assert (= 8 (length personnes)))
        (dotimes (i 8)
          (let ((position i))
            (push (sb-thread:make-thread
                    (lambda ()
                      (dotimes (iteration 20)
                        (declare (ignorable iteration))
                        (let ((sujet (mrjam-oidc:identite-sujet
                                      (mrjam-oidc:verifier-id-token
                                        (vision:json-object-get (nth position personnes) "token") jwks
                                        :client-id client :nonce nonce :maintenant maintenant :tolerance 0))))
                          (assert (equal sujet (format nil "00000000-0000-4000-8000-~12,'0D" (1+ position))))
                          (setf (aref resultats position) sujet))))) threads)))
        (dolist (thread threads) (sb-thread:join-thread thread))
        (assert (= 8 (length (remove-duplicates (coerce resultats 'list) :test #'equal))))
        (incf nombre 160)))
    (format t "~&OIDC ES256 : ~D cas/assertions terminés, signatures OpenSSL indépendantes et concurrence locale.~%" nombre)
    t))
