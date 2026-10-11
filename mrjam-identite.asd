(asdf:defsystem "mrjam-identite"
  :description "Client d'identité provisoire Keycloak ; aucun fournisseur ni maître IdP."
  :depends-on ("mrjam-courriel")
  :components ((:file "lisp/identite/keycloak")))
