(asdf:defsystem "mrjam-courriel"
  :description "File transactionnelle privée commune ; sans service au chargement."
  :depends-on ("mrjam-native")
  :serial t
  :components ((:file "lisp/courriel/package")
               (:file "lisp/courriel/prive")
               (:file "lisp/courriel/mime")
               (:file "lisp/courriel/file")
               (:file "lisp/courriel/transport")))
