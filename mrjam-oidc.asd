(asdf:defsystem "mrjam-oidc"
  :description "Vérification OIDC ES256 ; aucune connexion, session ou migration au chargement."
  :version "0.1.0"
  :depends-on ("mrjam-native" "cl-base64" "ironclad/public-key/secp256r1")
  :serial t
  :components ((:file "lisp/identite/oidc-package")
               (:file "lisp/identite/oidc-token"))
  :in-order-to ((asdf:test-op (asdf:test-op "mrjam-oidc/tests"))))

(asdf:defsystem "mrjam-oidc/tests"
  :depends-on ("mrjam-oidc")
  :components ((:file "tests/oidc-token"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (unless (uiop:symbol-call :mrjam-oidc-tests :verifier)
               (error "Échec des assertions OIDC."))))

(asdf:defsystem "mrjam-oidc/transactions"
  :description "Transactions OIDC/PKCE durables ; initialisation explicite hors chargement."
  :depends-on ("mrjam-oidc")
  :components ((:file "lisp/identite/oidc-transactions"))
  :in-order-to ((asdf:test-op (asdf:test-op "mrjam-oidc/transactions-tests"))))

(asdf:defsystem "mrjam-oidc/transactions-tests"
  :depends-on ("mrjam-oidc/transactions")
  :components ((:file "tests/oidc-transactions"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (unless (uiop:symbol-call :mrjam-oidc-transactions-tests :verifier)
               (error "Échec des transactions OIDC."))))
