(asdf:defsystem "mrjam-identite"
  :description "Adaptateurs d'identité ; aucun fournisseur ni maître IdP."
  :depends-on ("mrjam-courriel" "mrjam-oidc/transport")
  :serial t
  :components ((:file "lisp/identite/keycloak") (:file "lisp/identite/kanidm")))
